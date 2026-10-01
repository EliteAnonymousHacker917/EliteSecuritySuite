import os
import time
from datetime import timedelta
from collections import defaultdict

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ===========================
# CONFIG (SET THESE!)
# ===========================
LOG_CHANNEL_ID = 1554423238233161759          # channel ID for logs
AUTO_ROLE_ID = 0            # role ID to auto-assign on join

BLOCKED_KEYWORDS = [
    "telegram", "t.me", "zangi", "services.zangi",
    "mega files", "confidential correspondence",
    "dm me for all kind", "porn", "sex", "nude"
]

BLOCKED_LINKS = [
    "t.me", "telegram.me", "bit.ly", "tinyurl.com",
    "discord.gg/", "grabify", "iplogger", "gyazo.com"
]

MALWARE_EXTENSIONS = [
    ".exe", ".dll", ".scr", ".apk", ".jar", ".bat", ".cmd"
]

SPAM_LIMIT = 6
SPAM_WINDOW = 8

RAID_JOIN_LIMIT = 6
RAID_JOIN_WINDOW = 15

MENTION_LIMIT = 5

# ===========================
# STATE
# ===========================
user_messages = defaultdict(list)
recent_joins = []  # NO GLOBAL NEEDED
muted_users = set()

# ===========================
# UTILS
# ===========================
async def log(guild: discord.Guild, msg: str):
    if LOG_CHANNEL_ID == 0:
        return
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        try:
            await channel.send(msg)
        except:
            pass

def suspicious_link(content: str) -> bool:
    content = content.lower()
    return any(x in content for x in BLOCKED_LINKS)

def malware_link(content: str) -> bool:
    content = content.lower()
    return any(content.endswith(ext) for ext in MALWARE_EXTENSIONS)

def is_suspicious_account(member: discord.Member) -> bool:
    account_age_seconds = (discord.utils.utcnow() - member.created_at).total_seconds()
    no_avatar = member.avatar is None
    few_roles = len(member.roles) <= 1
    return account_age_seconds < 86400 and no_avatar and few_roles

# ===========================
# EVENTS
# ===========================
@bot.event
async def on_ready():
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game("Elite Security Suite (AGGRESSIVE)")
    )
    print(f"Bot is online as {bot.user}")

    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} slash commands.")


@bot.event
async def on_member_join(member: discord.Member):
    now = time.time()

    # Track joins (NO GLOBAL NEEDED)
    recent_joins.append((now, member.id))

    # Auto-role assignment
    if AUTO_ROLE_ID != 0:
        role = member.guild.get_role(AUTO_ROLE_ID)
        if role:
            try:
                await member.add_roles(role, reason="Auto-role assignment")
                await log(member.guild, f"✅ Auto-role {role.name} assigned to {member}.")
            except:
                pass

    # Clean old joins
    recent_joins[:] = [(ts, uid) for ts, uid in recent_joins if now - ts <= RAID_JOIN_WINDOW]

    # Anti-raid detection
    if len(recent_joins) >= RAID_JOIN_LIMIT:
        await log(member.guild, f"⚠️ RAID WARNING: {len(recent_joins)} joins in {RAID_JOIN_WINDOW}s.")
        for ts, uid in recent_joins:
            m = member.guild.get_member(uid)
            if m and is_suspicious_account(m):
                try:
                    await m.ban(reason="Aggressive anti-raid protection")
                    await log(member.guild, f"🔨 Auto-banned {m} (suspicious during raid).")
                except:
                    pass

    # Anti-VPN / bot-like accounts
    if is_suspicious_account(member):
        try:
            await member.ban(reason="Aggressive anti-VPN / bot detection")
            await log(member.guild, f"🔨 Auto-banned {member} (suspicious account).")
        except:
            pass


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.lower()

    # Keyword blocking
    if any(word in content for word in BLOCKED_KEYWORDS):
        try:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} message blocked.",
                delete_after=5
            )
            await log(message.guild, f"🛡️ Blocked keyword from {message.author}.")
        except:
            pass
        return

    # Link blocking
    if suspicious_link(content):
        try:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} suspicious link removed.",
                delete_after=5
            )
            await log(message.guild, f"🔗 Removed suspicious link from {message.author}.")
        except:
            pass
        return

    # Malware blocking
    if malware_link(content):
        try:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} malware-type file blocked.",
                delete_after=5
            )
            await log(message.guild, f"⚠️ Malware-type link blocked from {message.author}.")
        except:
            pass
        return

    # Ghost ping
    if message.mentions and message.content.strip() == "":
        try:
            await message.delete()
            await log(message.guild, f"👻 Ghost ping removed from {message.author}.")
        except:
            pass
        return

    # Mass mention
    if len(message.mentions) >= MENTION_LIMIT:
        try:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} too many mentions.",
                delete_after=5
            )
            await log(message.guild, f"⚠️ Mass mention removed from {message.author}.")
        except:
            pass
        return

    # Anti-spam
    now = time.time()
    uid = message.author.id
    user_messages[uid].append(now)
    user_messages[uid] = [ts for ts in user_messages[uid] if now - ts <= SPAM_WINDOW]

    if len(user_messages[uid]) >= SPAM_LIMIT:
        if uid not in muted_users:
            muted_users.add(uid)
            try:
                await message.author.timeout(
                    discord.utils.utcnow() + timedelta(minutes=2),
                    reason="Aggressive anti-spam"
                )
                await log(message.guild, f"🔇 Timed out {message.author} for spam.")
            except:
                pass

    await bot.process_commands(message)


# ===========================
# ANTI-NUKE PROTECTION
# ===========================
@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    await log(guild, f"⚠️ Channel deleted: #{channel.name}. Checking audit logs...")

    try:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            user = entry.user
            try:
                await user.ban(reason="Aggressive anti-channel deletion")
                await log(guild, f"🔨 Auto-banned {user} for deleting channel #{channel.name}.")
            except:
                pass
            break
    except:
        pass


@bot.event
async def on_guild_role_delete(role):
    guild = role.guild
    await log(guild, f"⚠️ Role deleted: {role.name}. Checking audit logs...")

    try:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
            user = entry.user
            try:
                await user.ban(reason="Aggressive anti-role deletion")
                await log(guild, f"🔨 Auto-banned {user} for deleting role {role.name}.")
            except:
                pass
            break
    except:
        pass


@bot.event
async def on_webhooks_update(channel):
    guild = channel.guild
    await log(guild, f"⚠️ Webhook change detected in #{channel.name}. Checking audit logs...")

    try:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
            user = entry.user
            try:
                webhooks = await channel.webhooks()
                for wh in webhooks:
                    await wh.delete(reason="Aggressive anti-webhook nukes")
                await user.ban(reason="Aggressive anti-webhook nukes")
                await log(guild, f"🔨 Auto-banned {user} and deleted webhooks in #{channel.name}.")
            except:
                pass
            break
    except:
        pass


# ===========================
# SLASH COMMANDS
# ===========================
@bot.tree.command(name="ping", description="Check bot status")
async def ping(interaction):
    await interaction.response.send_message(
        "Pong! 🟢 Elite Security Suite (AGGRESSIVE) is active.",
        ephemeral=True
    )


@bot.tree.command(name="status", description="Show all security systems")
async def status(interaction):
    msg = (
        "🛡 **Elite Security Suite (AGGRESSIVE) Status**\n"
        "- Keyword blocking: ON\n"
        "- Link blocking: ON\n"
        "- Malware blocking: ON\n"
        "- Anti-spam: ON (auto-timeout)\n"
        "- Anti-raid: ON (auto-ban suspicious)\n"
        "- Anti-mass-mention: ON\n"
        "- Anti-ghost ping: ON\n"
        "- Anti-webhook nukes: ON (auto-ban)\n"
        "- Anti-channel deletion: ON (auto-ban)\n"
        "- Anti-role deletion: ON (auto-ban)\n"
        "- Auto-role assignment: " + ("ON" if AUTO_ROLE_ID != 0 else "OFF") + "\n"
        "- Logging: " + ("ON" if LOG_CHANNEL_ID != 0 else "OFF")
    )
    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(name="lockdown", description="Lock the server (Admin only)")
async def lockdown(interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You are not an admin.", ephemeral=True)
        return

    for channel in interaction.guild.channels:
        try:
            await channel.set_permissions(
                interaction.guild.default_role,
                send_messages=False,
                connect=False
            )
        except:
            pass

    await interaction.response.send_message("🔒 Server is now in lockdown mode.", ephemeral=False)
    await log(interaction.guild, "🔒 Server lockdown activated (AGGRESSIVE).")


@bot.tree.command(name="slowmode", description="Set slowmode on this channel")
async def slowmode(interaction, seconds: int):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("You cannot manage channels.", ephemeral=True)
        return

    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.response.send_message(f"⏳ Slowmode set to {seconds}s.", ephemeral=False)


@bot.tree.command(name="autorole", description="Set auto-role ID (Admin only)")
async def autorole(interaction, role: discord.Role):
    global AUTO_ROLE_ID
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You are not an admin.", ephemeral=True)
        return

    AUTO_ROLE_ID = role.id
    await interaction.response.send_message(
        f"✅ Auto-role set to {role.name} (ID: {role.id}).",
        ephemeral=True
    )
    await log(interaction.guild, f"✅ Auto-role updated to {role.name}.")


@bot.tree.command(name="ban", description="Ban a user (Admin only)")
async def ban(interaction, member: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("You cannot ban members.", ephemeral=True)
        return

    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Banned {member} for: {reason}", ephemeral=False)
        await log(interaction.guild, f"🔨 {interaction.user} banned {member}: {reason}")
    except:
        await interaction.response.send_message("Failed to ban member.", ephemeral=True)


@bot.tree.command(name="kick", description="Kick a user (Admin only)")
async def kick(interaction, member: discord.Member, reason: str = "No reason provided"):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("You cannot kick members.", ephemeral=True)
        return

    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 Kicked {member} for: {reason}", ephemeral=False)
        await log(interaction.guild, f"👢 {interaction.user} kicked {member}: {reason}")
    except:
        await interaction.response.send_message("Failed to kick member.", ephemeral=True)


@bot.tree.command(name="clear", description="Clear messages in this channel (Admin only)")
async def clear(interaction, amount: int):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("You cannot manage messages.", ephemeral=True)
        return

    try:
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(
            f"🧹 Cleared {len(deleted)} messages.",
            ephemeral=False
        )
        await log(interaction.guild, f"🧹 {interaction.user} cleared {len(deleted)} messages in #{interaction.channel}.")
    except:
        await interaction.response.send_message("Failed to clear messages.", ephemeral=True)


# ===========================
# RUN
# ===========================
bot.run(os.getenv("DISCORD_TOKEN"))
