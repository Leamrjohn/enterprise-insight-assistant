from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.schemas.prompt_templates import (
    PromptTemplateCreate,
    PromptTemplateUpdate,
    PromptTemplateOut,
)
from app.services.prompt_template_service import (
    create_prompt_template_service,
    list_prompt_templates_service,
    get_prompt_template_by_id_service,
    update_prompt_template_service,
    delete_prompt_template_service,
)
from app.core.company_auth import CurrentCompanyContext, get_current_company_context
from app.db.session import get_db
from app.core.exceptions import DuplicatePromptTemplateError

router = APIRouter()


@router.post(
    "/prompt-templates",
    response_model=PromptTemplateOut,
    status_code=201,
)
def create_prompt_template(
    request_model: PromptTemplateCreate,
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    try:
        return create_prompt_template_service(
            db,
            context.user.id,
            request_model.name,
            request_model.template,
            request_model.description,
        )
    except DuplicatePromptTemplateError:
        raise HTTPException(
            status_code=409, detail="prompt template name already exists"
        )


@router.get(
    "/prompt-templates",
    response_model=list[PromptTemplateOut],
)
def list_prompt_templates(
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    return list_prompt_templates_service(
        db,
        context.user.id,
    )


@router.get(
    "/prompt-templates/{id}",
    response_model=PromptTemplateOut,
)
def get_prompt_template(
    id: int,
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    record = get_prompt_template_by_id_service(db, context.user.id, id)
    if record is None:
        raise HTTPException(status_code=404, detail="the prompt template is not found")
    return record


@router.patch(
    "/prompt-templates/{id}",
    response_model=PromptTemplateOut,
)
def update_prompt_template(
    id: int,
    request_model: PromptTemplateUpdate,
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    updates = request_model.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=422, detail="at least one field must have updates"
        )
    try:
        record = update_prompt_template_service(db, context.user.id, id, updates)
    except DuplicatePromptTemplateError:
        raise HTTPException(
            status_code=409, detail="prompt template name already exists"
        )
    if record is None:
        raise HTTPException(status_code=404, detail="the prompt template is not found")
    return record


@router.delete(
    "/prompt-templates/{id}",
    status_code=204,
)
def delete_prompt_template(
    id: int,
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    record = delete_prompt_template_service(db, context.user.id, id)
    if record is None:
        raise HTTPException(status_code=404, detail="the prompt template is not found")
