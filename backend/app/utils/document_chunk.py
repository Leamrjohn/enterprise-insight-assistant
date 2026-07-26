from pathlib import Path


def chunk_text(content: str, max_tokens: int = 512) -> list[str]:
    """将文本分块，每块不超过 max_tokens 个词。

    按段落切分；如果单个段落超长，则按词进一步切分。
    """
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buffer: list[str] = []
    token_count: int = 0

    for para in paragraphs:
        words = para.split()
        word_count = len(words)

        # ── 单个段落超长：直接按词切分 ──
        if word_count > max_tokens:
            # 先把当前 buffer 保存
            if buffer:
                chunks.append("\n\n".join(buffer))
                buffer = []
                token_count = 0
            # 把这个段落切成多块
            start = 0
            while start < len(words):
                end = start + max_tokens
                chunk_words = words[start:end]  # ← 知识点1
                chunks.append(" ".join(chunk_words))  # ← 知识点2
                start = end
            continue  # ← 知识点3

        # ── 正常段落：累积到 buffer ──
        if token_count + word_count > max_tokens and buffer:
            chunks.append("\n\n".join(buffer))
            buffer = []
            token_count = 0

        buffer.append(para)
        token_count += word_count

    if buffer:
        chunks.append("\n\n".join(buffer))

    return chunks


def chunk_file(file_path: Path) -> list[str]:
    """读取文件并分块。"""
    content = file_path.read_text(encoding="utf-8")
    return chunk_text(content)
