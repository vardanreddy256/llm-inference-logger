"""
Redis Streams consumer loop.
Uses consumer groups for at-least-once delivery and auto-ack on success.
"""
import asyncio
import logging
import redis.asyncio as aioredis

from app.config import settings
from app.pipeline import process_event

logger = logging.getLogger(__name__)


async def ensure_consumer_group(r: aioredis.Redis):
    """Create the consumer group if it doesn't already exist."""
    try:
        await r.xgroup_create(settings.stream_name, settings.consumer_group, id="0", mkstream=True)
        logger.info("Consumer group '%s' created.", settings.consumer_group)
    except Exception as exc:
        if "BUSYGROUP" in str(exc):
            logger.info("Consumer group '%s' already exists.", settings.consumer_group)
        else:
            raise


async def run_consumer():
    """Main consumer loop — polls Redis Streams and processes events."""
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    await ensure_consumer_group(r)

    logger.info(
        "Ingestion consumer started. stream=%s group=%s",
        settings.stream_name, settings.consumer_group,
    )

    while True:
        try:
            entries = await r.xreadgroup(
                groupname=settings.consumer_group,
                consumername=settings.consumer_name,
                streams={settings.stream_name: ">"},
                count=settings.batch_size,
                block=settings.poll_interval_ms,
            )

            if not entries:
                continue

            for _stream, messages in entries:
                for msg_id, fields in messages:
                    success = await process_event(fields)
                    if success:
                        await r.xack(settings.stream_name, settings.consumer_group, msg_id)
                    else:
                        # Leave unacknowledged for retry / dead-letter handling
                        logger.warning("Event %s left unacked for retry", msg_id)

        except asyncio.CancelledError:
            logger.info("Consumer loop cancelled, shutting down.")
            break
        except Exception as exc:
            logger.error("Consumer error: %s — retrying in 2s", exc)
            await asyncio.sleep(2)

    await r.aclose()
