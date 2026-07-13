from app.tools.protocol import Tool, ToolInput, ToolOutput
from app.core.rag.embeddings_local import LocalEmbeddingProvider
from app.repositories.vector_repository import search_similar_chunks
from app.core.rag.engine import EvidenceRef, build_prompt, check_sufficiency
from app.db.session import SessionLocal


class RAGTool(Tool):
    @property
    def name(self) -> str:
        return "rag_search"

    @property
    def description(self) -> str:
        return "在已上传的文档中搜索相关内容，用于回答需要的文档支撑的问题"

    def execute(self, input: ToolInput) -> ToolOutput:
        question = input.parameters.get("question")
        user_id = input.parameters.get("user_id")
        if not question or not user_id:
            return ToolOutput(success=False, error="缺少参数")

        embedder = LocalEmbeddingProvider()
        embedding = embedder.embed(question)

        db = SessionLocal()
        try:
            results = search_similar_chunks(
                db=db, embedding=embedding, user_id=user_id, top_k=3, min_score=0.3
            )
            evidences = [
                EvidenceRef(chunk_id=r["chunk_id"], document_id=r["document_id"],
                            content=r["content"], score=r["score"])
                for r in results
            ]
            if not check_sufficiency(evidences, question=question):
                return ToolOutput(success=True, data={"answer": "无法回答：资料不足"})
            prompt = build_prompt(question, evidences)

            return ToolOutput(success=True, data={
                "evidences": [{"content": e.content, "score": e.score} for e in evidences],
                "prompt": prompt,
            })
        finally:
            db.close()
