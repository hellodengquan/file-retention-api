import logging
from datetime import datetime, timedelta
from typing import Callable, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, JobEvent
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    retry_if_exception_type
)

from app.config import settings
from app.database import SessionLocal
from app import crud
from app.models import AuditLog, FileRecord

logger = logging.getLogger(__name__)

MAX_RETRY_ATTEMPTS = settings.SCHEDULER_MAX_RETRY_ATTEMPTS
RETRY_MIN_WAIT = settings.SCHEDULER_RETRY_MIN_WAIT_SECONDS
RETRY_MAX_WAIT = settings.SCHEDULER_RETRY_MAX_WAIT_SECONDS


def log_job_failure(job_id: str, exception: Exception):
    db = SessionLocal()
    try:
        audit_log = AuditLog(
            user_id=None,
            username="system",
            action=f"scheduler_{job_id}_failed",
            resource_type="scheduler",
            resource_id=None,
            details=f"调度任务执行失败: {str(exception)}",
            ip_address="system"
        )
        db.add(audit_log)
        db.commit()
    except Exception as e:
        logger.error(f"记录任务失败日志时出错: {str(e)}")
        db.rollback()
    finally:
        db.close()


def scheduler_event_listener(event: JobEvent):
    if event.exception:
        logger.error(
            f"任务 {event.job_id} 执行异常: {str(event.exception)}",
            exc_info=event.exception
        )
        log_job_failure(event.job_id, event.exception)
    if hasattr(event, 'scheduled_run_times') and event.code == EVENT_JOB_MISSED:
        logger.warning(f"任务 {event.job_id} 错过执行时间: {event.scheduled_run_times}")


@retry(
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    retry=retry_if_exception_type((Exception,)),
    reraise=True
)
def process_expired_files_with_retry():
    db = SessionLocal()
    try:
        expired_files = crud.get_expired_files(db)
        archived_count = 0
        deleted_count = 0
        failed_count = 0

        for file in expired_files:
            try:
                policy = file.policy
                action = policy.action_on_expiry if policy else "archive"

                if action == "delete":
                    file.status = "deleted"
                    deleted_count += 1
                    log_action = "auto_delete"
                    log_detail = f"系统自动删除过期文件: {file.file_name}"
                else:
                    file.status = "archived"
                    file.archived_at = datetime.utcnow()
                    archived_count += 1
                    log_action = "auto_archive"
                    log_detail = f"系统自动归档过期文件: {file.file_name}"

                audit_log = AuditLog(
                    user_id=None,
                    username="system",
                    action=log_action,
                    resource_type="file",
                    resource_id=file.id,
                    details=log_detail,
                    ip_address="system"
                )
                db.add(audit_log)
            except Exception as file_e:
                failed_count += 1
                logger.error(f"处理文件 {file.id}({file.file_name}) 时失败: {str(file_e)}")
                continue

        db.commit()
        if archived_count > 0 or deleted_count > 0 or failed_count > 0:
            logger.info(
                f"过期文件处理完成: 归档 {archived_count} 个, 删除 {deleted_count} 个, 失败 {failed_count} 个"
            )
        if failed_count > 0:
            raise RuntimeError(f"有 {failed_count} 个文件处理失败")
    except Exception as e:
        db.rollback()
        logger.error(f"处理过期文件时出错: {str(e)}")
        raise
    finally:
        db.close()


def process_expired_files():
    try:
        process_expired_files_with_retry()
    except Exception as e:
        logger.error(f"过期文件处理任务经过 {MAX_RETRY_ATTEMPTS} 次重试后仍然失败: {str(e)}")
        log_job_failure("process_expired_files", e)
        fallback_process_expired_files()


def fallback_process_expired_files():
    logger.warning("启动过期文件处理兜底逻辑：仅标记处理状态，不执行实际归档/删除")
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        threshold = now - timedelta(hours=24)
        audit_log = AuditLog(
            user_id=None,
            username="system",
            action="scheduler_fallback_process_expired_files",
            resource_type="scheduler",
            details="过期文件处理触发兜底逻辑，请管理员检查系统",
            ip_address="system"
        )
        db.add(audit_log)
        db.commit()
    except Exception as e:
        logger.error(f"兜底逻辑执行失败: {str(e)}")
        db.rollback()
    finally:
        db.close()


@retry(
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    retry=retry_if_exception_type((Exception,)),
    reraise=True
)
def update_file_expiry_dates_with_retry():
    db = SessionLocal()
    try:
        active_files = db.query(FileRecord).filter(FileRecord.status == "active").all()
        updated_count = 0

        for file in active_files:
            policy = crud.get_policy_by_category(db, file.business_category)
            if policy:
                new_expiry = file.upload_date + timedelta(days=policy.retention_days)
                if file.last_extended_at and file.expiry_date:
                    extension_days = (file.expiry_date - (file.upload_date + timedelta(days=policy.retention_days))).days
                    if extension_days > 0:
                        new_expiry = new_expiry + timedelta(days=extension_days)
                if file.expiry_date != new_expiry:
                    file.expiry_date = new_expiry
                    updated_count += 1

        db.commit()
        if updated_count > 0:
            logger.info(f"文件过期时间更新完成: 更新 {updated_count} 个文件")
    except Exception as e:
        db.rollback()
        logger.error(f"更新文件过期时间时出错: {str(e)}")
        raise
    finally:
        db.close()


def update_file_expiry_dates():
    try:
        update_file_expiry_dates_with_retry()
    except Exception as e:
        logger.error(f"更新文件过期时间任务经过 {MAX_RETRY_ATTEMPTS} 次重试后仍然失败: {str(e)}")
        log_job_failure("update_file_expiry_dates", e)


scheduler = BackgroundScheduler()


def start_scheduler():
    scheduler.add_listener(scheduler_event_listener, EVENT_JOB_ERROR | EVENT_JOB_MISSED)

    scheduler.add_job(
        process_expired_files,
        trigger=IntervalTrigger(minutes=settings.SCHEDULER_INTERVAL_MINUTES),
        id="process_expired_files",
        name="处理过期文件",
        replace_existing=True,
        next_run_time=datetime.now(),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300
    )

    scheduler.add_job(
        update_file_expiry_dates,
        trigger=IntervalTrigger(hours=24),
        id="update_file_expiry_dates",
        name="更新文件过期时间",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600
    )

    scheduler.start()
    logger.info("调度器已启动")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("调度器已停止")
