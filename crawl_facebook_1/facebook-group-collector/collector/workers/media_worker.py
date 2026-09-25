"""
collector/workers/media_worker.py — Independent Media Download Worker.

Consumes MediaJobItem from media_queue, downloads binary file via HTTP,
computes SHA-256 hash, stores in sharded path structure, updates MediaRepo
metadata, and links to post/comment owner.
"""
from __future__ import annotations

import logging
import aiofiles

from collector.config import MediaConfig
from collector.downloaders.media_downloader import MediaDownloader
from collector.metrics.emitter import MetricsCounters
from collector.pipeline.items import MediaJobItem
from collector.pipeline.worker import BaseWorker
from collector.storage.layout import StorageLayout
from collector.storage.repository import CommentRepo, MediaRepo, PostRepo

logger = logging.getLogger(__name__)


class MediaWorker(BaseWorker):
    """
    Worker that consumes MediaJobItem from media_queue and downloads
    media files asynchronously without blocking browser or comment workers.
    """

    def __init__(
        self,
        name: str,
        queue,
        counters: MetricsCounters,
        layout: StorageLayout,
        group_slug: str,
        config: MediaConfig,
        downloader: Optional[MediaDownloader] = None,
        max_retries: int = 3,
    ):
        super().__init__(
            name=name,
            queue=queue,
            counters=counters,
            max_retries=max_retries,
        )
        self.layout = layout
        self.group_slug = group_slug
        self.media_repo = MediaRepo(layout)
        self.post_repo = PostRepo(layout, group_slug)
        self.downloader = downloader or MediaDownloader(
            timeout_sec=config.download_timeout_sec,
            max_retries=config.max_retries,
        )

    async def process_item(self, item: MediaJobItem) -> None:
        """Download media binary, compute SHA-256, store, and record metadata."""
        if not isinstance(item, MediaJobItem):
            logger.warning("%s received unexpected item: %s", self.name, type(item))
            return

        if not item.source_url:
            return

        # 1. Upsert pending record
        pending_record, _ = await self.media_repo.upsert_by_url({
            "source_url": item.source_url,
            "media_type": item.media_type,
            "owner_type": item.owner_type,
            "owner_id": item.owner_id,
            "position": item.position,
        })
        media_id = pending_record["id"]

        try:
            # 2. Download binary & hash
            result = await self.downloader.download(item.source_url)

            # 3. Save to sharded disk path
            file_path = await MediaDownloader.save_to_disk(self.layout, result)
            relative_storage_uri = str(file_path.relative_to(self.layout.root))

            # Also save to organized human-inspectable group images folder
            named_image_path = None
            if item.owner_type == "post" and item.owner_id:
                named_image_path = self.layout.group_post_image_path(
                    self.group_slug, item.owner_id, item.position, result.ext
                )
            elif item.owner_type == "comment" and item.owner_id:
                named_image_path = self.layout.group_comment_image_path(
                    self.group_slug, item.owner_id, item.position, result.ext
                )

            if named_image_path:
                named_image_path.parent.mkdir(parents=True, exist_ok=True)
                if not named_image_path.exists():
                    async with aiofiles.open(named_image_path, "wb") as f:
                        await f.write(result.content)

            # 4. Mark downloaded & check SHA-256 deduplication
            existing_id = await self.media_repo.mark_downloaded(
                media_id=media_id,
                sha256=result.sha256,
                storage_uri=relative_storage_uri,
                mime_type=result.mime_type,
                file_size=result.file_size,
            )

            final_media_id = existing_id or media_id

            if existing_id:
                self._counters.media_deduped += 1
                logger.info(
                    "Media SHA-256 DEDUP: url=%s already exists as %s",
                    item.source_url[:60], existing_id,
                )
            else:
                self._counters.media_downloaded += 1
                logger.debug(
                    "Media downloaded: id=%s sha256=%s bytes=%d",
                    media_id, result.sha256[:12], result.file_size,
                )

            # 5. Extract CIC credit report info if media is an image
            cic_dict = None
            if item.media_type == "photo" or (result.mime_type and "image" in result.mime_type):
                try:
                    from collector.analysis.cic_extractor import CICExtractor
                    img_to_scan = named_image_path if (named_image_path and named_image_path.exists()) else file_path
                    info = await CICExtractor.extract_from_image(img_to_scan)
                    if info.is_cic:
                        cic_dict = info.to_dict()
                        await self.media_repo.update_cic_data(final_media_id, cic_dict)
                        logger.info(
                            "CIC Report extracted for media=%s: score=%s tier=%s date=%s provider=%s",
                            final_media_id, info.score, info.tier, info.scoring_date, info.provider,
                        )
                except Exception as e:
                    logger.debug("CIC extraction failed for media %s: %s", final_media_id, e)

            # 6. Link media to owner
            if item.owner_type == "post" and item.owner_id:
                post = await self.post_repo.get(item.owner_id)
                if post:
                    media_ids = post.get("media_ids", [])
                    if final_media_id not in media_ids:
                        media_ids.append(final_media_id)
                    post["media_ids"] = media_ids
                    if cic_dict:
                        post["cic_data"] = cic_dict
                    path = self.layout.post_path(self.group_slug, item.owner_id)
                    from collector.storage.json_store import write_json
                    await write_json(path, post)

                    # Central customer registry in cic_customers.json
                    if cic_dict and any(cic_dict.get(k) for k in ("customer_name", "phone_number", "id_card_number", "cic_code")):
                        try:
                            leads_path = self.layout.group_cic_leads_path(self.group_slug)
                            from collector.storage.json_store import read_json
                            existing_leads = (await read_json(leads_path)) or []
                            lead_entry = {
                                "post_id": item.owner_id,
                                "post_url": post.get("post_url"),
                                "media_id": final_media_id,
                                "customer_name": cic_dict.get("customer_name"),
                                "date_of_birth": cic_dict.get("date_of_birth"),
                                "cic_code": cic_dict.get("cic_code"),
                                "address": cic_dict.get("address"),
                                "phone_number": cic_dict.get("phone_number"),
                                "id_card_number": cic_dict.get("id_card_number"),
                                "score": cic_dict.get("score"),
                                "tier": cic_dict.get("tier"),
                                "scoring_date": cic_dict.get("scoring_date"),
                                "provider": cic_dict.get("provider"),
                            }
                            # Dedup by cic_code or id_card_number
                            match_idx = -1
                            for idx, e in enumerate(existing_leads):
                                if (lead_entry["cic_code"] and e.get("cic_code") == lead_entry["cic_code"]) or \
                                   (lead_entry["id_card_number"] and e.get("id_card_number") == lead_entry["id_card_number"]):
                                    match_idx = idx
                                    break
                            if match_idx >= 0:
                                existing_leads[match_idx].update(lead_entry)
                            else:
                                existing_leads.append(lead_entry)
                            await write_json(leads_path, existing_leads)
                        except Exception as e:
                            logger.debug("Failed updating cic_customers.json: %s", e)
            elif item.owner_type == "comment" and item.owner_id and item.post_id:
                comment_repo = CommentRepo(self.layout, item.post_id)
                comment = await comment_repo.get(item.owner_id)
                if comment:
                    media_ids = comment.get("media_ids", [])
                    if final_media_id not in media_ids:
                        media_ids.append(final_media_id)
                    comment["media_ids"] = media_ids
                    if cic_dict:
                        comment["cic_data"] = cic_dict
                    c_path = self.layout.comment_path(item.post_id, item.owner_id)
                    from collector.storage.json_store import write_json
                    await write_json(c_path, comment)

        except Exception as e:
            logger.error("Failed downloading media %s: %s", item.source_url, e)
            self._counters.errors += 1
            # Mark error status on media record
            meta_path = self.layout.media_meta_path(media_id)
            from collector.storage.json_store import read_json, write_json
            data = await read_json(meta_path)
            if data:
                data["download_status"] = "error"
                await write_json(meta_path, data)
            raise
