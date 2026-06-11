import re


class TextVocabulary:
    def __init__(self, tokens):
        unique_tokens = ["<unk>"]
        unique_tokens.extend(sorted(set(tokens) - {"<unk>"}))
        self._token_to_index = {token: index for index, token in enumerate(unique_tokens)}
        self._default_index = self._token_to_index["<unk>"]

    def __getitem__(self, token):
        return self._token_to_index.get(token, self._default_index)

    def __len__(self):
        return len(self._token_to_index)


def get_text_tokenizer(tokenizer_type):
    if tokenizer_type != "basic_english":
        raise ValueError(f"Unsupported tokenizer_type={tokenizer_type!r}. Only 'basic_english' is supported.")
    return lambda text: re.findall(r"\b\w+\b|[^\w\s]", text.lower())


def build_text_vocab(token_iter):
    tokens = []
    for item_tokens in token_iter:
        tokens.extend(item_tokens)
    return TextVocabulary(tokens)
