from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.modules.identity.authentication import (
    create_access_token,
    get_authenticated_account,
    get_current_user,
)
from app.modules.identity.models import User
from app.modules.identity.schemas import (
    AccessTokenOut,
    CurrentUserOut,
    CurrentUserUpdate,
    InitialPasswordSetup,
    LoginRequest,
    OwnerBootstrapRequest,
    PasswordChangeRequest,
)
from app.modules.organizations.access import (
    CurrentCompanyContext,
    get_current_company_context,
)
from app.modules.organizations.schemas import (
    MembershipApplicationOut,
    MembershipApplicationReapply,
    MembershipApplicationRegister,
    MembershipApplicationRegistered,
)
from app.modules.organizations.service import (
    bootstrap_first_company_owner,
    reapply_to_same_company,
    register_membership_application,
)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/bootstrap-owner", response_model=AccessTokenOut, status_code=201)
def bootstrap_owner(
    request: OwnerBootstrapRequest, db: Session = Depends(get_db)
) -> AccessTokenOut:
    try:
        result = bootstrap_first_company_owner(
            db,
            name=request.name,
            username=request.username,
            password=request.password,
            company_name=request.company_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="用户名已存在")
    token, expires_in = create_access_token(user=result.user)
    return AccessTokenOut(access_token=token, expires_in=expires_in)


@router.post("/login", response_model=AccessTokenOut)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> AccessTokenOut:
    user = db.query(User).filter(User.username == request.username).first()
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户尚未启用或已被禁用")
    token, expires_in = create_access_token(user=user)
    return AccessTokenOut(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=CurrentUserOut)
def read_current_user(
    context: CurrentCompanyContext = Depends(get_current_company_context),
) -> CurrentUserOut:
    return CurrentUserOut(
        id=context.user.id,
        name=context.user.name,
        username=context.user.username,
        role=context.role,
        is_active=context.user.is_active,
        created_at=context.user.created_at,
        company_id=context.company.id,
        company_name=context.company.name,
        membership_status=context.membership.status,
    )


@router.patch("/me", response_model=CurrentUserOut)
def update_current_user(
    request: CurrentUserUpdate,
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
) -> CurrentUserOut:
    context.user.name = request.name
    db.commit()
    db.refresh(context.user)
    return read_current_user(context)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(status_code=422, detail="当前密码不正确")
    current_user.password_hash = hash_password(request.new_password)
    current_user.auth_version += 1
    db.commit()


@router.post("/initial-password", status_code=status.HTTP_204_NO_CONTENT)
def set_initial_password(
    request: InitialPasswordSetup,
    account: User = Depends(get_authenticated_account),
    db: Session = Depends(get_db),
) -> None:
    """One-time API-key migration path for existing local accounts."""
    if account.password_hash is not None or account.username is not None:
        raise HTTPException(status_code=409, detail="该账户已设置密码登录")
    account.username = request.username
    account.password_hash = hash_password(request.password)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="用户名已存在")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Invalidate every currently issued browser token for this account."""
    current_user.auth_version += 1
    db.commit()


@router.post(
    "/membership-applications",
    response_model=MembershipApplicationRegistered,
    status_code=status.HTTP_201_CREATED,
)
def register_application(
    request: MembershipApplicationRegister,
    db: Session = Depends(get_db),
) -> MembershipApplicationRegistered:
    try:
        result = register_membership_application(
            db,
            name=request.name,
            username=request.username,
            password=request.password,
            invitation_code=request.invitation_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="account already has an application"
        )
    return MembershipApplicationRegistered(
        id=result.application.id,
        user_id=result.application.user_id,
        status=result.application.status,
        created_at=result.application.created_at,
        reviewed_at=result.application.reviewed_at,
    )


@router.post(
    "/membership-applications/reapply",
    response_model=MembershipApplicationOut,
)
def reapply_application(
    request: MembershipApplicationReapply,
    db: Session = Depends(get_db),
) -> MembershipApplicationOut:
    try:
        application = reapply_to_same_company(
            db,
            username=request.username,
            password=request.password,
            invitation_code=request.invitation_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return MembershipApplicationOut.model_validate(application)
