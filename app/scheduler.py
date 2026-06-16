import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal
from app import crud
from app.models import AuditLog

logger = logging.getLogger(__name__)


def process_expired_files():
    db = SessionLocal()
    try:
        expired_files = crud.get_expired_files(db)
        archived_count = 0
        deleted_count = 0

        for file in expired_files:
            policy = file.policy
            action = policy.action_on_expiry if policy else "archive"

            if action == "delete":
                file.status = "deleted"
                deleted_count += 1
                log_action = "auto_delete"
                log_detail = f"系统自动删除过期文件: {file.file_name}"
            else:
                file.status = "archived"
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

        db.commit()
        if archived_count > 0 or deleted_count > 0:
            logger.info(
                f"过期文件处理完成: 归档 {archived_count} 个, 删除 {deleted_count} 个"
            )
    except Exception as e:
        logger.error(f"处理过期文件时出错: {str(e)}")
        db.rollback()
    finally:
        db.close()


def update_file_expiry_dates():
    db = SessionLocal()
    try:
        from app.models import FileRecord
        from datetime import timedelta

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
        logger.error(f"更新文件过期时间时出错: {str(e)}")
        db.rollback()
    finally:
        db.close()


scheduler = BackgroundScheduler()


def start_scheduler():
    scheduler.add_job(
        process_expired_files,
        trigger=IntervalTrigger(minutes=settings.SCHEDULER_INTERVAL_MINUTES),
        id="process_expired_files",
        name="处理过期文件",
        replace_existing=True,
        next_run_time=datetime.now()
    )

    scheduler.add_job(
        update_file_expiry_dates,
        trigger=IntervalTrigger(hours=24),
        id="update_file_expiry_dates",
        name="更新文件过期时间",
        replace_existing=True
    )

    scheduler.start()
    logger.info("调度器已启动")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("调度器已停止")
