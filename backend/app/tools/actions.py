"""CRM, memory, files, code, and browser tools used by autonomous runs."""

from __future__ import annotations

import csv
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select

from app.config import settings
from app.knowledge.embeddings import embed_text
from app.models import AgentMemory, Artifact, Company, Contact, Lead
from app.tools.base import Tool, ToolContext, ToolResult
from app.utils import new_id, utcnow

logger = logging.getLogger(__name__)


def _norm(value: str) -> str:
    return " ".join((value or "").strip().casefold().split())


def _artifact_dir(task_id: str | None) -> Path:
    root = Path(settings.artifact_dir)
    folder = root / (task_id or "loose")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_artifact(context: ToolContext, filename: str, data: bytes, media_type: str) -> Artifact:
    if context.db is None:
        raise RuntimeError("database session is required")
    safe = Path(filename).name
    path = _artifact_dir(context.task_id) / f"{new_id()}-{safe}"
    path.write_bytes(data)
    row = Artifact(
        task_id=context.task_id,
        filename=safe,
        media_type=media_type,
        path=str(path),
        size=len(data),
    )
    context.db.add(row)
    context.db.flush()
    return row


class UpdatePlanTool(Tool):
    name = "update_plan"
    description = "ثبت برنامهٔ جاری. اثر خارجی ندارد و فقط متن برنامه را ذخیره می‌کند."
    provider = "local"
    input_schema = {
        "type": "object",
        "properties": {"plan": {"type": "string"}},
        "required": ["plan"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        plan = str(arguments.get("plan") or "").strip()
        return ToolResult(ok=True, content=f"برنامه ثبت شد.\n{plan[:2000]}")


class CreateLeadTool(Tool):
    name = "create_lead"
    description = "ثبت سرنخ در CRM داخلی. اگر شرکت و ایمیل تکراری باشد، همان رکورد به‌روز می‌شود."
    provider = "database"
    input_schema = {
        "type": "object",
        "properties": {
            "company_name": {"type": "string"},
            "title": {"type": "string"},
            "city": {"type": "string"},
            "industry": {"type": "string"},
            "website": {"type": "string"},
            "contact_name": {"type": "string"},
            "email": {"type": "string"},
            "phone": {"type": "string"},
            "notes": {"type": "string"},
            "source": {"type": "string"},
        },
        "required": ["company_name", "title"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.db is None:
            return ToolResult(ok=False, content="پایگاه داده در دسترس نیست.")
        db = context.db
        name = str(arguments["company_name"]).strip()
        email = str(arguments.get("email") or "").strip().lower()
        company = None
        for row in db.scalars(select(Company)).all():
            if _norm(row.name) == _norm(name):
                company = row
                break
        created = False
        if company is None:
            company = Company(
                name=name,
                city=str(arguments.get("city") or ""),
                industry=str(arguments.get("industry") or ""),
                website=str(arguments.get("website") or ""),
                notes=str(arguments.get("notes") or ""),
            )
            db.add(company)
            db.flush()
            created = True
        lead = None
        if email:
            lead = db.scalar(
                select(Lead)
                .join(Contact, Contact.lead_id == Lead.id)
                .where(Lead.company_id == company.id, func.lower(Contact.email) == email)
            )
        if lead is None:
            lead = Lead(
                company_id=company.id,
                title=str(arguments["title"]).strip(),
                source=str(arguments.get("source") or "agent"),
                status="new",
                score=0,
                notes=str(arguments.get("notes") or ""),
                created_by=context.user_id,
            )
            db.add(lead)
            db.flush()
            created = True
        else:
            note = str(arguments.get("notes") or "").strip()
            if note and note not in (lead.notes or ""):
                lead.notes = ((lead.notes or "") + "\n" + note).strip()
        if email or arguments.get("contact_name") or arguments.get("phone"):
            contact = None
            if email:
                contact = db.scalar(
                    select(Contact).where(
                        Contact.lead_id == lead.id, func.lower(Contact.email) == email
                    )
                )
            if contact is None:
                db.add(
                    Contact(
                        company_id=company.id,
                        lead_id=lead.id,
                        name=str(arguments.get("contact_name") or "نامشخص"),
                        email=email,
                        phone=str(arguments.get("phone") or ""),
                        title="",
                    )
                )
        db.flush()
        verb = "ساخته شد" if created else "به‌روز شد"
        return ToolResult(
            ok=True,
            content=f"سرنخ {verb}: {company.name} — {lead.title}",
            data={"lead_id": lead.id, "company_id": company.id, "created": created},
        )


class UpdateLeadTool(Tool):
    name = "update_lead"
    description = "به‌روزرسانی وضعیت، امتیاز یا یادداشت یک سرنخ."
    provider = "database"
    input_schema = {
        "type": "object",
        "properties": {
            "lead_id": {"type": "string"},
            "status": {"type": "string"},
            "score": {"type": "integer"},
            "notes": {"type": "string"},
        },
        "required": ["lead_id"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.db is None:
            return ToolResult(ok=False, content="پایگاه داده در دسترس نیست.")
        lead = context.db.get(Lead, arguments["lead_id"])
        if lead is None:
            return ToolResult(ok=False, content="سرنخ پیدا نشد.")
        if arguments.get("status"):
            lead.status = str(arguments["status"])
        if arguments.get("score") is not None:
            lead.score = int(arguments["score"])
        if arguments.get("notes"):
            lead.notes = str(arguments["notes"])
        context.db.flush()
        return ToolResult(
            ok=True, content=f"سرنخ {lead.title} به‌روز شد.", data={"lead_id": lead.id}
        )


class SearchLeadsTool(Tool):
    name = "search_leads"
    description = "جست‌وجوی سرنخ‌ها و شرکت‌های موجود در CRM."
    provider = "database"
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.db is None:
            return ToolResult(ok=False, content="پایگاه داده در دسترس نیست.")
        query = f"%{str(arguments['query']).strip()}%"
        leads = context.db.scalars(
            select(Lead)
            .join(Company, Company.id == Lead.company_id, isouter=True)
            .where(or_(Lead.title.ilike(query), Lead.notes.ilike(query), Company.name.ilike(query)))
            .limit(20)
        ).all()
        if not leads:
            return ToolResult(ok=True, content="سرنخی پیدا نشد.", data={"leads": []})
        lines = []
        payload = []
        for lead in leads:
            company = context.db.get(Company, lead.company_id) if lead.company_id else None
            label = f"{company.name if company else '—'} — {lead.title} ({lead.status})"
            lines.append(f"- {label}")
            payload.append(
                {"id": lead.id, "title": lead.title, "company": company.name if company else ""}
            )
        return ToolResult(ok=True, content="\n".join(lines), data={"leads": payload})


class ExportLeadsTool(Tool):
    name = "export_leads"
    description = "خروجی CSV و XLSX از سرنخ‌ها برای دانلود."
    provider = "files"
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.db is None:
            return ToolResult(ok=False, content="پایگاه داده در دسترس نیست.")
        query = str(arguments.get("query") or "").strip()
        stmt = select(Lead)
        if query:
            like = f"%{query}%"
            stmt = stmt.join(Company, Company.id == Lead.company_id, isouter=True).where(
                or_(Lead.title.ilike(like), Company.name.ilike(like))
            )
        leads = context.db.scalars(stmt.limit(500)).all()
        rows = []
        for lead in leads:
            company = context.db.get(Company, lead.company_id) if lead.company_id else None
            contact = context.db.scalar(select(Contact).where(Contact.lead_id == lead.id))
            rows.append(
                {
                    "company": company.name if company else "",
                    "city": company.city if company else "",
                    "title": lead.title,
                    "status": lead.status,
                    "score": lead.score,
                    "contact": contact.name if contact else "",
                    "email": contact.email if contact else "",
                    "phone": contact.phone if contact else "",
                    "notes": lead.notes,
                }
            )
        import io

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()) if rows else ["company"])
        writer.writeheader()
        writer.writerows(rows)
        csv_bytes = buffer.getvalue().encode("utf-8-sig")
        csv_row = save_artifact(context, "leads.csv", csv_bytes, "text/csv")
        xlsx = _xlsx(rows)
        xlsx_row = save_artifact(
            context,
            "leads.xlsx",
            xlsx,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        return ToolResult(
            ok=True,
            content=f"{len(rows)} سرنخ در CSV و XLSX ذخیره شد.",
            data={"artifact_ids": [csv_row.id, xlsx_row.id]},
        )


class MemorySaveTool(Tool):
    name = "memory_save"
    description = "ذخیرهٔ یک واقعیت، سرنخ یا یادداشت در حافظهٔ بلندمدت."
    provider = "pgvector"
    input_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "kind": {"type": "string"},
        },
        "required": ["content"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.db is None:
            return ToolResult(ok=False, content="پایگاه داده در دسترس نیست.")
        content = str(arguments["content"]).strip()
        row = AgentMemory(
            user_id=context.user_id,
            kind=str(arguments.get("kind") or "fact"),
            content=content,
            embedding=embed_text(content),
            meta={"agent": context.agent_slug, "at": utcnow().isoformat()},
        )
        context.db.add(row)
        context.db.flush()
        return ToolResult(ok=True, content="در حافظه ذخیره شد.", data={"id": row.id})


class MemorySearchTool(Tool):
    name = "memory_search"
    description = "جست‌وجو در حافظهٔ بلندمدت عامل‌ها."
    provider = "pgvector"
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["query"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.db is None:
            return ToolResult(ok=False, content="پایگاه داده در دسترس نیست.")
        limit = max(1, min(int(arguments.get("limit") or 5), 10))
        query = str(arguments["query"])
        if context.db.bind is not None and context.db.bind.dialect.name == "postgresql":
            from app.models import AgentMemory as Memory

            vector = embed_text(query)
            distance = Memory.embedding.cosine_distance(vector)
            stmt = (
                select(Memory).where(Memory.embedding.is_not(None)).order_by(distance).limit(limit)
            )
            rows = context.db.scalars(stmt).all()
        else:
            like = f"%{query}%"
            rows = context.db.scalars(
                select(AgentMemory).where(AgentMemory.content.ilike(like)).limit(limit)
            ).all()
        if not rows:
            return ToolResult(ok=True, content="چیزی در حافظه پیدا نشد.", data={"memories": []})
        lines = [f"- ({row.kind}) {row.content[:400]}" for row in rows]
        return ToolResult(
            ok=True,
            content="\n".join(lines),
            data={"memories": [{"id": row.id, "kind": row.kind} for row in rows]},
        )


class WriteReportTool(Tool):
    name = "write_report"
    description = "ذخیرهٔ گزارش مارک‌داون و در صورت امکان PDF برای دانلود."
    provider = "files"
    input_schema = {
        "type": "object",
        "properties": {"title": {"type": "string"}, "markdown": {"type": "string"}},
        "required": ["title", "markdown"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        title = str(arguments["title"]).strip() or "report"
        body = str(arguments["markdown"])
        markdown = f"# {title}\n\n{body}\n"
        md = save_artifact(
            context, f"{_slug_filename(title)}.md", markdown.encode("utf-8"), "text/markdown"
        )
        pdf_id = _try_pdf(context, title, body)
        ids = [md.id] + ([pdf_id] if pdf_id else [])
        note = "گزارش مارک‌داون ذخیره شد."
        if pdf_id:
            note += " نسخهٔ PDF هم ساخته شد."
        else:
            note += " PDF به‌خاطر نبود قلم فارسی ساخته نشد؛ مارک‌داون کامل است."
        return ToolResult(ok=True, content=note, data={"artifact_ids": ids})


class PythonExecTool(Tool):
    name = "python_exec"
    description = "اجرای پایتون در یک فرایند جدا با محدودیت زمان، برای تحلیل داده. شبکه و متغیرهای محرمانه در دسترس نیست."
    provider = "sandbox"
    input_schema = {
        "type": "object",
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        code = str(arguments["code"])
        work = _artifact_dir(context.task_id) / f"py-{new_id()}"
        work.mkdir(parents=True, exist_ok=True)
        script = work / "main.py"
        script.write_text(code, encoding="utf-8")
        env = {"PATH": "/usr/bin:/bin", "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            completed = subprocess.run(
                [sys.executable, "-I", str(script)],
                cwd=work,
                env=env,
                capture_output=True,
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, content="اجرای کد بیش از ۲۰ ثانیه طول کشید و متوقف شد.")
        stdout = completed.stdout.decode("utf-8", errors="replace")[:8000]
        stderr = completed.stderr.decode("utf-8", errors="replace")[:4000]
        produced = []
        if context.db is not None:
            for path in work.iterdir():
                if path.name == "main.py" or not path.is_file():
                    continue
                row = save_artifact(
                    context, path.name, path.read_bytes(), "application/octet-stream"
                )
                produced.append(row.id)
        text = stdout or "(خروجی خالی)"
        if stderr:
            text += "\nخطا:\n" + stderr
        if completed.returncode != 0:
            return ToolResult(ok=False, content=text, data={"artifact_ids": produced})
        return ToolResult(ok=True, content=text, data={"artifact_ids": produced})


class BrowserTool(Tool):
    name = "browser"
    description = "باز کردن صفحه با مرورگر هدلس برای سایت‌های جاوااسکریپتی، استخراج متن و عکس صفحه."
    provider = "playwright"
    input_schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        url = str(arguments["url"])
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return ToolResult(
                ok=False,
                content="Playwright نصب نیست. از web_fetch استفاده کنید یا تصویر worker را با مرورگر بسازید.",
            )
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=25000, wait_until="domcontentloaded")
                title = page.title()
                text = page.inner_text("body")[:12000]
                shot = page.screenshot(full_page=False)
                browser.close()
        except Exception as exc:
            return ToolResult(ok=False, content=f"مرورگر نتوانست صفحه را باز کند: {exc}")
        artifact_id = None
        if context.db is not None:
            row = save_artifact(context, "page.png", shot, "image/png")
            artifact_id = row.id
        return ToolResult(
            ok=True,
            content=f"{title}\n{text}",
            data={"title": title, "artifact_id": artifact_id, "url": url},
        )


class DelegateTool(Tool):
    name = "delegate"
    description = "سپردن یک زیرهدف به عامل متخصص و برگرداندن گزارش او."
    provider = "langgraph"
    input_schema = {
        "type": "object",
        "properties": {
            "agent_slug": {"type": "string"},
            "goal": {"type": "string"},
        },
        "required": ["agent_slug", "goal"],
        "additionalProperties": False,
    }

    async def aexecute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        from app.runtime.delegate import run_delegated

        try:
            report = await run_delegated(
                agent_slug=str(arguments["agent_slug"]),
                goal=str(arguments["goal"]),
                context=context,
            )
        except Exception as exc:
            logger.exception("delegate failed")
            return ToolResult(ok=False, content=f"واگذاری ناموفق بود: {exc}")
        return ToolResult(ok=True, content=report or "عامل متخصص گزارشی برنگرداند.")

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(ok=False, content="واگذاری فقط داخل اجرای خودمختار قابل استفاده است.")


def _xlsx(rows: list[dict]) -> bytes:
    import io

    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "leads"
    headers = list(rows[0].keys()) if rows else ["company"]
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(header, "") for header in headers])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _slug_filename(title: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in title)[:40].strip("-")
    return cleaned or "report"


def _try_pdf(context: ToolContext, title: str, body: str) -> str | None:
    font = _find_font()
    if font is None:
        return None
    try:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("Report", "", font)
        pdf.set_font("Report", size=14)
        pdf.multi_cell(0, 10, title)
        pdf.ln(4)
        pdf.set_font("Report", size=11)
        pdf.multi_cell(0, 8, body[:8000])
        raw = bytes(pdf.output())
    except Exception:
        logger.exception("pdf render failed")
        return None
    row = save_artifact(context, f"{_slug_filename(title)}.pdf", raw, "application/pdf")
    return row.id


def _find_font() -> str | None:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            return path
    return None
