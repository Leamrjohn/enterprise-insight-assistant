"""T11b: what this company already concluded, read back by a node's model.

memory_search finds only the user's own validated conclusions, through the same
filters the planner's memory selection uses.  report_search finds the company's
finished reports by keyword and report_export reads one; both show a report
only when everything it drew on is readable by the caller now: a report must
not become a way round document permissions.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.modules.analysis.tool_protocol import ToolOutput
from app.modules.documents.models import Documents
from app.modules.documents.repository import allowed_min_view_roles
from app.modules.memory.service import (
    MIN_RELEVANCE,
    memory_relevance,
    select_planner_memories,
)
from app.modules.organizations.models import CompanyMember
from app.modules.runtime.tools.context import RuntimeContext
from app.modules.workflow.models import (
    AnalysisTask,
    AnalysisTaskInputArtifactVersion,
)

MAX_MEMORIES = 5
MAX_REPORTS = 5
# Only the newest finished tasks are scanned, so one search stays bounded.
SCAN_LIMIT = 100
MAX_REPORT_CHARS = 6000
FINISHED = frozenset({"completed", "partial"})


def memory_search(
    db: Session, context: RuntimeContext, arguments: dict[str, Any]
) -> Any:
    memories, _manifest = select_planner_memories(
        db,
        company_id=context.company_id,
        user_id=context.actor_id,
        question=arguments["query"],
        limit=MAX_MEMORIES,
        record_use=False,  # a lookup is not a use the memory ranking should learn from
    )
    return {"memories": memories}


def report_readable(db: Session, context: RuntimeContext, task: AnalysisTask) -> bool:
    """True only if the caller may read this task's report now.

    All four must hold (the user's rule, T11b):
    1. task.company_id is context.company_id;
    2. task.status is in FINISHED and task.result_data holds a "report";
    3. every document the report cites (report["document_citations"], each
       with a "document_id") is in this company and visible to the caller's
       current role (CompanyMember, as in documents.readable_document_ids);
       a citation without a document_id cannot be checked, so it denies;
    4. if the task used any attachment (AnalysisTaskInputArtifactVersion rows
       of task.id), the caller is the task's own user (task.user_id).
    """
    if task.company_id != context.company_id:
        return False
    result_data = task.result_data or {}  # an unfinished task may have none
    if not (task.status in FINISHED and result_data.get("report")):
        return False
    membership = (
        db.query(CompanyMember)
        .filter(
            CompanyMember.company_id == context.company_id,
            CompanyMember.user_id == context.actor_id,
        )
        .one_or_none()
    )
    if membership is None:
        return False
    citations = result_data["report"].get("document_citations") or []
    document_ids = {citation.get("document_id") for citation in citations}
    if None in document_ids:  # a citation we cannot check denies
        return False
    visible = {
        document_id
        for (document_id,) in db.query(Documents.id)
        .filter(
            Documents.id.in_(document_ids),
            Documents.company_id == context.company_id,
            Documents.min_view_role.in_(allowed_min_view_roles(membership.role)),
        )
        .all()
    }
    if document_ids - visible:  # some cited document is not readable now
        return False
    used_attachment = (
        db.query(AnalysisTaskInputArtifactVersion.task_id)
        .filter(AnalysisTaskInputArtifactVersion.task_id == task.id)
        .first()
    )
    return used_attachment is None or task.user_id == context.actor_id


def _first_sentence(text: str) -> str:
    return text.split("。", 1)[0][:120]


def report_search(
    db: Session, context: RuntimeContext, arguments: dict[str, Any]
) -> Any:
    """The company's finished reports that match the words and the caller may read."""
    candidates = (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.company_id == context.company_id,
            AnalysisTask.status.in_(FINISHED),
            AnalysisTask.id != context.task_id,
        )
        .order_by(AnalysisTask.id.desc())
        .limit(SCAN_LIMIT)
        .all()
    )
    found = []
    for task in candidates:
        summary = ((task.result_data or {}).get("report") or {}).get(
            "executive_summary", ""
        )
        relevance = memory_relevance(arguments["query"], f"{task.question} {summary}")
        # Cheap words first; the permission check runs only on a match.
        if relevance >= MIN_RELEVANCE and report_readable(db, context, task):
            found.append((relevance, task, summary))
    found.sort(key=lambda item: item[0], reverse=True)  # ties stay newest first
    return {
        "reports": [
            {
                "task_id": task.id,
                "question": task.question,
                "completed_at": task.completed_at,
                "summary": _first_sentence(summary),
            }
            for _relevance, task, summary in found[:MAX_REPORTS]
        ]
    }


def _render(report: dict[str, Any]) -> str:
    sections = [f"摘要：{report.get('executive_summary', '')}"]
    for title, items, field in (
        ("已确认事实", report.get("confirmed_facts"), "statement"),
        ("假设", report.get("hypotheses"), "statement"),
        ("建议", report.get("recommendations"), "action"),
        ("限制", report.get("limitations"), "message"),
    ):
        lines = [f"- {item[field]}" for item in items or [] if item.get(field)]
        if lines:
            sections.append(f"{title}：\n" + "\n".join(lines))
    return "\n\n".join(sections)


def report_export(
    db: Session, context: RuntimeContext, arguments: dict[str, Any]
) -> Any:
    task = db.get(AnalysisTask, arguments["task_id"])
    if task is None or not report_readable(db, context, task):
        # The same answer whether the report is missing, unfinished or forbidden.
        return ToolOutput(
            success=False,
            error="没有这份可读报告。",
            error_code="tool_arguments_invalid",
            repairable=True,
            model_feedback="没有这份可读报告；任务编号请用 report_search 的 task_id 或 memory_search 的 source_task_id。",
        )
    text = _render((task.result_data or {})["report"])  # readable means a report
    return {
        "task_id": task.id,
        "question": task.question,
        "text": text[:MAX_REPORT_CHARS],
        "truncated": len(text) > MAX_REPORT_CHARS,
    }
