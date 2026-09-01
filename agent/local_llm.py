"""A language model that runs on this laptop's CPU, for no money.

Every other model in this portfolio is fitted by us and small. This one is not
ours and is not small, and it exists because the portfolio kept describing an
LLM seam it never exercised. `docs/adr/007-provider-agnostic-llm-seam.md`
committed to a `complete(system, user) -> str` contract with adapters for
`openai_compatible` and `anthropic`, and then no reported number ever went
through it -- deliberately, because a metric that depends on a vendor, a model
version and a sampling temperature is not reproducible by a reviewer.

A local model resolves that tension rather than trading it away. It is a third
adapter behind the same contract, it costs nothing, and it is *reproducible*:
greedy decoding, fixed weights, no network at inference time. A reviewer with
the same machine gets the same tokens.

**What it is not.** Qwen2.5-0.5B is roughly a thousandth the size of a frontier
model. Nothing measured with it should be read as what an LLM can do -- only as
what *this* LLM does, which is the honest scope and is stated wherever the
numbers appear.

Measured on the development machine (Intel Core i7-8650U, 4 cores, no GPU):
3.14 tokens/second generating 128 tokens from a 219-token prompt. That number
sets the whole design -- it is why tool-selection calls are capped at 48 tokens
and stopped early, and why the evaluation set is sized in tens of tasks rather
than hundreds.
"""
import os
import time
from dataclasses import dataclass

DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"

# Four physical cores. torch defaults to the logical count, and oversubscribing
# a matmul-bound workload measures the scheduler rather than the model.
DEFAULT_THREADS = 4


@dataclass
class Completion:
    text: str
    prompt_tokens: int
    completion_tokens: int
    seconds: float

    @property
    def tokens_per_second(self):
        return self.completion_tokens / self.seconds if self.seconds else 0.0


class LocalModel:
    """Implements the portfolio's `complete(system, user) -> str` seam locally.

    Loading is deferred to first use. Importing this module must stay cheap,
    because the evaluation harness imports it to read `DEFAULT_MODEL` even on
    runs that never generate a token.
    """

    def __init__(self, model_id=DEFAULT_MODEL, threads=DEFAULT_THREADS, dtype="float32"):
        self.model_id = model_id
        self.threads = threads
        self.dtype_name = dtype
        self._model = None
        self._tokenizer = None
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.seconds = 0.0

    def _load(self):
        if self._model is not None:
            return
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch.set_num_threads(self.threads)
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_id, dtype=getattr(torch, self.dtype_name)
        )
        self._model.eval()

    def complete(self, system, user, max_new_tokens=128, stop=None):
        """Greedy, deterministic completion. Returns a `Completion`.

        `stop` truncates generation as soon as the model emits one of the given
        strings. For tool-selection calls that is most of the saving: the model
        emits a short JSON object and would otherwise keep writing commentary
        for another forty tokens at three tokens per second.
        """
        self._load()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        text = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        encoded = self._tokenizer(text, return_tensors="pt")
        prompt_length = int(encoded["input_ids"].shape[-1])

        options = {}
        if stop:
            options["stop_strings"] = list(stop)
            options["tokenizer"] = self._tokenizer

        started = time.perf_counter()
        with self._torch.no_grad():
            generated = self._model.generate(
                **encoded,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self._tokenizer.eos_token_id,
                **options,
            )
        elapsed = time.perf_counter() - started

        produced = generated[0][prompt_length:]
        completion = Completion(
            text=self._tokenizer.decode(produced, skip_special_tokens=True),
            prompt_tokens=prompt_length,
            completion_tokens=int(produced.shape[-1]),
            seconds=elapsed,
        )
        self.calls += 1
        self.prompt_tokens += completion.prompt_tokens
        self.completion_tokens += completion.completion_tokens
        self.seconds += elapsed
        return completion

    def usage(self):
        return {
            "model": self.model_id,
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "seconds": round(self.seconds, 1),
            "tokens_per_second": (
                round(self.completion_tokens / self.seconds, 2) if self.seconds else 0.0
            ),
        }
