"""Document routes infer company scope from the approved membership."""

from fastapi.testclient import TestClient

from app.modules.identity.authentication import get_current_user
from app.main import app
from app.modules.organizations.models import CompanyMember
from app.modules.identity.models import User


def test_document_routes_ignore_client_company_id(
    client: TestClient, db_session, test_user: User
) -> None:
    first_company = client.post("/companies", json={"name": "first"}).json()
    document = client.post(
        "/documents",
        json={
            "name": "first.txt",
            "content": "第一家公司合同资料",
            "source": "manual",
            "company_id": 99999,
        },
    )
    assert document.status_code == 202
    assert document.json()["company_id"] == first_company["id"]

    other_user = User(name="other", api_key="other-api-key")
    db_session.add(other_user)
    db_session.flush()
    second_company = client.post("/companies", json={"name": "not-used"})
    assert second_company.status_code == 409
    # A second company is created directly for this isolated test actor; the
    # request below is still made through its own approved member context.
    from app.modules.organizations.models import Company

    other_company = Company(name="second")
    db_session.add(other_company)
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=other_company.id,
            user_id=other_user.id,
            role="owner",
            status="approved",
        )
    )
    db_session.flush()

    app.dependency_overrides[get_current_user] = lambda: other_user
    try:
        cross_company = client.get(f"/documents/{document.json()['id']}")
        assert cross_company.status_code == 404
    finally:
        app.dependency_overrides[get_current_user] = lambda: test_user
