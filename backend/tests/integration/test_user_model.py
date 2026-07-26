from uuid import uuid4
from sqlalchemy.orm import Session

from app.core.security import hash_api_key
from app.models.user import User


def test_create_user(db_session: Session) -> None:
    api_key = uuid4().hex
    user = User(name="test-user", api_key=api_key)
    db_session.add(user)
    db_session.flush()

    # 验证字段
    assert user.id is not None
    assert user.name == "test-user"
    assert user.api_key == api_key
    assert user.role == "user"
    assert user.created_at is not None

    # 数据库只按哈希查询，不保存可还原的明文 key。
    found = (
        db_session.query(User)
        .filter(User.api_key_hash == hash_api_key(api_key))
        .first()
    )
    assert found is not None
    assert found.id == user.id
    assert found.name == "test-user"

    # 按 id 查询
    by_id = db_session.query(User).filter(User.id == user.id).first()
    assert by_id is not None
    assert by_id.api_key == api_key


def test_api_key_uniqueness(db_session: Session) -> None:
    api_key = uuid4().hex
    user1 = User(name="user-a", api_key=api_key)
    db_session.add(user1)
    db_session.flush()

    user2 = User(name="user-b", api_key=api_key)
    db_session.add(user2)

    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db_session.flush()
