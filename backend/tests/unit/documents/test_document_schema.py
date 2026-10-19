from app.modules.documents.schemas import DocumentOut


def test_document_out_allows_none_content():

    document_out = DocumentOut(
        id=1,
        uploaded_by_user_id=7,
        name="pending.pdf",
        content=None,
        source="upload",
        status="failed",
        error_message="无法解析文档",
    )
    assert document_out.content is None
    assert document_out.error_message == "无法解析文档"
