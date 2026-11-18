import asyncio
import hashlib
import io
import json
import os
import random
import time
from pathlib import Path

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Image

PLUGIN_NAME = "tafei_sticker"
EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
MAX_STICKER_BYTES = 8 * 1024 * 1024


def _project_root() -> str:
    root = os.environ.get("ASTRBOT_ROOT") or ""
    if root:
        return os.path.dirname(os.path.abspath(root))
    return str(Path(__file__).resolve().parents[4])


def _load_local_config(root: str) -> dict:
    path = os.path.join(root, ".secrets", "tafei.env.json")
    try:
        with io.open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


PROJECT_ROOT = _project_root()
_LOCAL_CONFIG = _load_local_config(PROJECT_ROOT)
STICKER_DIR = os.environ.get("TAFEI_STICKER_DIR") or _LOCAL_CONFIG.get(
    "sticker_dir"
) or os.path.join(PROJECT_ROOT, "stickers", "tafei")
NAPCAT_API = (
    os.environ.get("TAFEI_NAPCAT_API")
    or _LOCAL_CONFIG.get("napcat_api")
    or "http://127.0.0.1:3000"
).rstrip("/")
NAPCAT_TOKEN = (
    os.environ.get("TAFEI_NAPCAT_TOKEN")
    or _LOCAL_CONFIG.get("napcat_token")
    or ""
)


def _data_dir() -> str:
    root = os.environ.get("ASTRBOT_ROOT") or ""
    if root:
        return os.path.join(root, "data")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(here)), "data")


def _md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def _valid_image(body: bytes, ext: str) -> bool:
    if ext in (".jpg", ".jpeg"):
        return body.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return body.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".gif":
        return body.startswith((b"GIF87a", b"GIF89a"))
    if ext == ".webp":
        return len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP"
    return False


class TafeiSticker(star.Star):
    """塔菲表情包：回复后按概率补一张，启动时同步一次塔菲号收藏。"""

    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        self.cfg_dir = os.path.join(_data_dir(), "plugin_data", PLUGIN_NAME)
        os.makedirs(self.cfg_dir, exist_ok=True)
        self.cfg_path = os.path.join(self.cfg_dir, "config.json")
        self.manifest_path = os.path.join(self.cfg_dir, "remote.json")
        self.cfg = self._load()
        self.meta = self._load_meta()
        self._recent: dict = {}
        self._last_ts: dict = {}
        self._sync_task = None
        try:
            self._sync_task = asyncio.create_task(self._startup_sync())
        except Exception as e:
            logger.error(f"tafei_sticker: 启动同步任务失败 {e}")

    def _load(self) -> dict:
        default = {"enabled": True, "probability": 0.3, "cooldown_seconds": 30}
        try:
            with io.open(self.cfg_path, encoding="utf-8") as f:
                default.update(json.load(f))
        except Exception:
            pass
        try:
            default["probability"] = max(
                0.0, min(1.0, float(default.get("probability", 0.3)))
            )
        except (TypeError, ValueError):
            default["probability"] = 0.3
        return default

    def _save(self) -> None:
        with io.open(self.cfg_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.cfg, ensure_ascii=False, indent=2))

    def _load_meta(self) -> dict:
        path = os.path.join(STICKER_DIR, "meta.json")
        try:
            self._meta_mtime = os.path.getmtime(path)
            with io.open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            self._meta_mtime = 0
            return {}

    def _maybe_reload_meta(self) -> None:
        path = os.path.join(STICKER_DIR, "meta.json")
        try:
            mt = os.path.getmtime(path)
        except OSError:
            return
        if mt != getattr(self, "_meta_mtime", 0):
            self.meta = self._load_meta()

    def _match(self, text: str) -> list:
        """按 meta.json 里的关键词匹配，返回可能的文件路径列表。"""
        if not text:
            return []
        self._maybe_reload_meta()
        out = []
        for name, info in (self.meta or {}).items():
            p = os.path.join(STICKER_DIR, name)
            if not os.path.exists(p):
                continue
            if any(k and k in text for k in info.get("kw", [])):
                out.append(p)
        return out

    def _files(self) -> list:
        if not os.path.isdir(STICKER_DIR):
            return []
        out = []
        for name in sorted(os.listdir(STICKER_DIR)):
            if name.lower().endswith(EXTS):
                p = os.path.join(STICKER_DIR, name)
                try:
                    if os.path.getsize(p) > 1000:
                        out.append(p)
                except OSError:
                    pass
        return out

    # ---------- 收藏同步 ----------
    async def _sync_once(self) -> int:
        import aiohttp

        headers = {}
        if NAPCAT_TOKEN:
            headers["Authorization"] = "Bearer " + NAPCAT_TOKEN
        async with aiohttp.ClientSession() as sess:
            async with sess.post(
                NAPCAT_API + "/fetch_custom_face",
                json={"count": 100},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
        urls = [u for u in (data.get("data") or []) if isinstance(u, str)]
        if not urls:
            return 0

        os.makedirs(STICKER_DIR, exist_ok=True)
        local = {}
        for p in self._files():
            try:
                with open(p, "rb") as f:
                    local[_md5(f.read())] = p
            except OSError:
                pass

        try:
            with io.open(self.manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = {}

        added = 0
        keep = {}
        async with aiohttp.ClientSession() as sess:
            for url in urls:
                key = _md5(url.encode("utf-8"))[:10]
                name = manifest.get(key, "")
                if name and os.path.exists(os.path.join(STICKER_DIR, name)):
                    keep[key] = name
                    continue
                try:
                    async with sess.get(
                        url, timeout=aiohttp.ClientTimeout(total=20)
                    ) as r:
                        body = await r.read()
                        ctype = r.headers.get("content-type", "")
                except Exception as e:
                    logger.warning(f"tafei_sticker: 下载失败 {url} {e}")
                    continue
                if len(body) < 1000 or len(body) > MAX_STICKER_BYTES:
                    continue
                h = _md5(body)
                if h in local:
                    keep[key] = os.path.basename(local[h])
                    continue
                ext = ".png" if "png" in ctype else ".gif" if "gif" in ctype else ".jpg"
                if not ctype.startswith("image/") or not _valid_image(body, ext):
                    logger.warning(f"tafei_sticker: 忽略非图片响应 {url}")
                    continue
                fname = f"fav_{key}{ext}"
                target = os.path.join(STICKER_DIR, fname)
                temp_target = target + ".part"
                with open(temp_target, "wb") as f:
                    f.write(body)
                os.replace(temp_target, target)
                local[h] = os.path.join(STICKER_DIR, fname)
                keep[key] = fname
                added += 1

        for key, name in list(manifest.items()):
            # Only remote favorites are managed here. Never delete manually
            # supplied or curated sticker files during a refresh.
            if key not in keep and os.path.basename(name).startswith("fav_"):
                p = os.path.join(STICKER_DIR, name)
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

        with io.open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(keep, f, ensure_ascii=False, indent=2)
        self.meta = self._load_meta()
        return added

    async def _startup_sync(self) -> None:
        """上线时同步一次；机器人早于 NapCat 起来时重试到成功为止。"""
        await asyncio.sleep(5)
        for _ in range(40):
            try:
                added = await self._sync_once()
                logger.info(
                    f"tafei_sticker: 上线同步完成，新增 {added} 张，"
                    f"共 {len(self._files())} 张"
                )
                return
            except Exception as e:
                logger.debug(f"tafei_sticker: 同步失败，稍后重试（{e}）")
                await asyncio.sleep(30)

    # ---------- 发送 ----------
    def _pick(self, key: str = "") -> str:
        files = self._files()
        if not files:
            return None
        recent = self._recent.get(key, [])
        pool = [p for p in files if p not in recent] or files
        path = random.choice(pool)
        self._recent[key] = (recent + [path])[-2:]
        return path

    @filter.on_decorating_result()
    async def maybe_sticker(self, event: AstrMessageEvent) -> None:
        if not self.cfg.get("enabled", True):
            return
        try:
            result = event.get_result()
        except Exception:
            return
        if not result or not getattr(result, "chain", None):
            return
        chain = result.chain
        for seg in chain:
            if seg.__class__.__name__ == "Image":
                return
        text = "".join(
            seg.text for seg in chain if isinstance(getattr(seg, "text", None), str)
        )
        # 只有塔菲这句话命中了某个表情的含义才会补图，没命中就不发
        matched = self._match(text)
        if not matched:
            return
        key = event.unified_msg_origin
        now = time.time()
        if now - self._last_ts.get(key, 0) < float(
            self.cfg.get("cooldown_seconds", 30)
        ):
            return
        if random.random() >= float(self.cfg.get("probability", 0.3)):
            return
        recent = self._recent.get(key, [])
        pool = [p for p in matched if p not in recent] or matched
        path = random.choice(pool)
        self._recent[key] = (recent + [path])[-2:]
        try:
            chain.append(Image.fromFileSystem(path))
            self._last_ts[key] = now
            logger.info(f"tafei_sticker: attached {os.path.basename(path)} -> {key}")
        except Exception as e:
            logger.error(f"tafei_sticker: 附加失败 {e}")

    @filter.command("st")
    async def st(self, event: AstrMessageEvent) -> None:
        path = self._pick(event.unified_msg_origin)
        if not path:
            yield event.plain_result("表情目录是空的喵")
            return
        event.set_extra("_tafei_sticker_sent", True)
        yield event.image_result(path)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("st_p")
    async def st_p(self, event: AstrMessageEvent, value: str = "") -> None:
        try:
            v = float(str(value).strip())
        except ValueError:
            yield event.plain_result(
                f"当前概率 {self.cfg.get('probability')}，用法 /st_p 0.3"
            )
            return
        v = max(0.0, min(1.0, v))
        self.cfg["probability"] = v
        self._save()
        yield event.plain_result(f"概率设成 {v}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("st_sync")
    async def st_sync(self, event: AstrMessageEvent) -> None:
        try:
            added = await self._sync_once()
            yield event.plain_result(
                f"同步完成，新增 {added} 张，现在一共 {len(self._files())} 张"
            )
        except Exception as e:
            yield event.plain_result(f"同步失败：{e}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("st_off")
    async def st_off(self, event: AstrMessageEvent) -> None:
        self.cfg["enabled"] = False
        self._save()
        yield event.plain_result("自动补图已关闭")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("st_on")
    async def st_on(self, event: AstrMessageEvent) -> None:
        self.cfg["enabled"] = True
        self._save()
        yield event.plain_result(
            f"自动补图已开启，概率 {self.cfg.get('probability')}"
        )

    @filter.command("st_list")
    async def st_list(self, event: AstrMessageEvent) -> None:
        files = self._files()
        if not files:
            yield event.plain_result("表情目录是空的喵")
            return
        names = "、".join(os.path.basename(p) for p in files)
        yield event.plain_result(f"现在有 {len(files)} 张：{names}")
