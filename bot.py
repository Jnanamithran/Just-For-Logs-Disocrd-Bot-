import discord
import sqlite3
import asyncio
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv(".env")
TOKEN = os.getenv("DISCORD_TOKEN")

# Intents and bot setup
intents = discord.Intents.default()
intents.members = True  # To track member join/leave events
intents.voice_states = True  # To track VC events
intents.message_content = True  # To track message content
bot = commands.Bot(command_prefix="!", intents=intents)

# Database setup
conn = sqlite3.connect("bot_database.db")
cursor = conn.cursor()

# Create or update tables
cursor.execute("""
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    member_log_channel_id INTEGER,
    vc_log_channel_id INTEGER,
    nickname_log_channel_id INTEGER,
    message_log_channel_id INTEGER
)
""")
conn.commit()


def set_log_channel(guild_id, channel_id, log_type):
    valid_log_types = ["member_log", "vc_log", "nickname_log", "message_log"]  # Include message_log here
    if log_type not in valid_log_types:
        raise ValueError(f"Invalid log type: {log_type}")
    
    column = f"{log_type}_channel_id"
    cursor.execute(f"""
    INSERT INTO guild_settings (guild_id, {column})
    VALUES (?, ?)
    ON CONFLICT(guild_id) DO UPDATE SET {column} = excluded.{column}
    """, (guild_id, channel_id))
    conn.commit()


def get_log_channel(guild_id, log_type):
    valid_log_types = ["member_log", "vc_log", "nickname_log", "message_log"]
    if log_type not in valid_log_types:
        return None
    column = f"{log_type}_channel_id"
    cursor.execute(f"SELECT {column} FROM guild_settings WHERE guild_id = ?", (guild_id,))
    result = cursor.fetchone()
    return result[0] if result else None

# Commands for log channels
@bot.tree.command(name="set_member_log", description="Set the log channel for member events")
async def set_member_log(interaction: discord.Interaction, channel: discord.TextChannel):
    set_log_channel(interaction.guild_id, channel.id, "member_log")
    await interaction.response.send_message(f"Member log channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="set_vc_log", description="Set the log channel for VC events")
async def set_vc_log(interaction: discord.Interaction, channel: discord.TextChannel):
    set_log_channel(interaction.guild_id, channel.id, "vc_log")
    await interaction.response.send_message(f"VC log channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="set_nickname_log", description="Set the log channel for nickname changes")
async def set_nickname_log(interaction: discord.Interaction, channel: discord.TextChannel):
    set_log_channel(interaction.guild_id, channel.id, "nickname_log")
    await interaction.response.send_message(f"Nickname log channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="set_message_log", description="Set the log channel for messages sent")
async def set_message_log(interaction: discord.Interaction, channel: discord.TextChannel):
    set_log_channel(interaction.guild_id, channel.id, "message_log")
    await interaction.response.send_message(f"Message log channel set to {channel.mention}", ephemeral=True)

# Events for logging
@bot.event
async def on_member_join(member):
    channel_id = get_log_channel(member.guild.id, "member_log")
    if channel_id:
        channel = bot.get_channel(channel_id)
        embed = discord.Embed(title="Member Joined", description=f"{member.mention} joined the server.", color=discord.Color.green())
        embed.set_footer(text=f"User ID: {member.id}")
        embed.timestamp = datetime.utcnow()
        await channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    channel_id = get_log_channel(member.guild.id, "member_log")
    if channel_id:
        channel = bot.get_channel(channel_id)
        embed = discord.Embed(title="Member Left", description=f"{member.mention} left the server.", color=discord.Color.red())
        embed.set_footer(text=f"User ID: {member.id}")
        embed.timestamp = datetime.utcnow()
        await channel.send(embed=embed)

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel is None and after.channel is not None:
        channel_id = get_log_channel(member.guild.id, "vc_log")
        if channel_id:
            channel = bot.get_channel(channel_id)
            embed = discord.Embed(
                title="Voice Channel Join",
                description=f"{member.mention} joined the voice channel {after.channel.mention}.",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"User ID: {member.id}")
            embed.timestamp = datetime.utcnow()
            await channel.send(embed=embed)

    elif before.channel is not None and after.channel is None:
        channel_id = get_log_channel(member.guild.id, "vc_log")
        if channel_id:
            channel = bot.get_channel(channel_id)
            embed = discord.Embed(
                title="Voice Channel Leave",
                description=f"{member.mention} left the voice channel {before.channel.mention}.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"User ID: {member.id}")
            embed.timestamp = datetime.utcnow()
            await channel.send(embed=embed)

    elif before.channel != after.channel:
        # User moved from one channel to another
        channel_id = get_log_channel(member.guild.id, "vc_log")
        if channel_id:
            channel = bot.get_channel(channel_id)

            try:
                # Look for the member_move action in the audit logs
                async for entry in member.guild.audit_logs(limit=10, action=discord.AuditLogAction.member_move):
                    if entry.target and entry.target.id == member.id:  # Ensure entry.target is not None
                        moved_by = entry.user.mention
                        embed = discord.Embed(
                            title="Voice Channel Moved",
                            description=f"{member.mention} was moved from {before.channel.mention} to {after.channel.mention} by {moved_by}.",
                            color=discord.Color.blue()
                        )
                        embed.set_footer(text=f"User ID: {member.id}")
                        embed.timestamp = datetime.utcnow()
                        await channel.send(embed=embed)
                        break
                else:
                    # No mover found, check if the user moved themselves or was dragged by someone
                    if before.channel != after.channel:
                        # Assume the user was dragged by someone else, as no audit log was found
                        moved_by = member.mention  # Tagging the user
                        embed = discord.Embed(
                            title="Voice Channel Moved",
                            description=f"{member.mention} was dragged from {before.channel.mention} to {after.channel.mention} by {moved_by}.",
                            color=discord.Color.blue()
                        )
                        embed.set_footer(text=f"User ID: {member.id}")
                        embed.timestamp = datetime.utcnow()
                        await channel.send(embed=embed)
            except Exception as e:
                print(f"Error finding mover: {e}")

@bot.event
async def on_member_update(before, after):
    if before.nick != after.nick:
        channel_id = get_log_channel(after.guild.id, "nickname_log")
        if channel_id:
            log_channel = bot.get_channel(channel_id)
            if log_channel:
                embed = discord.Embed(
                    title="Nickname Changed",
                    description=f"{after.name}'s nickname has been updated.",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Old Nickname", value=before.nick or "None", inline=False)
                embed.add_field(name="New Nickname", value=after.nick, inline=False)

                async for entry in after.guild.audit_logs(limit=10, action=discord.AuditLogAction.member_update):
                    if entry.target.id == after.id:
                        embed.add_field(name="Changed By", value=entry.user.mention, inline=False)
                        break
                else:
                    embed.add_field(name="Changed By", value="Unknown", inline=False)

                await log_channel.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    channel_id = get_log_channel(message.guild.id, "message_log")
    if channel_id:
        log_channel = bot.get_channel(channel_id)
        if log_channel:
            embed = discord.Embed(
                title="Message Sent",
                description=f"{message.author.mention} sent a message in {message.channel.mention}.",
                color=discord.Color.blue()
            )
            embed.add_field(name="Message Content", value=message.content[:1024] or "No content", inline=False)
            embed.set_footer(text=f"User ID: {message.author.id}")
            embed.timestamp = datetime.utcnow()

            await log_channel.send(embed=embed)



@bot.tree.command(name="activity", description="Change the bot's activity")
@app_commands.describe(
    activity_type="The type of activity (playing, listening, watching, streaming)", 
    activity_name="The name of the activity",
    stream_url="The URL for streaming (required for 'streaming' activity)"
)
async def set_activity(interaction: discord.Interaction, activity_type: str, activity_name: str, stream_url: str = None):
    # Check if the user is authorized
    if interaction.user.id != 722036964584587284:  # Replace with your actual user ID
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return

    activity = None

    if activity_type.lower() == "playing":
        activity = discord.Game(name=activity_name)
    elif activity_type.lower() == "listening":
        activity = discord.Activity(type=discord.ActivityType.listening, name=activity_name)
    elif activity_type.lower() == "watching":
        activity = discord.Activity(type=discord.ActivityType.watching, name=activity_name)
    elif activity_type.lower() == "streaming":
        if not stream_url:
            await interaction.response.send_message("You must provide a streaming URL for the 'streaming' activity type.", ephemeral=True)
            return
        activity = discord.Streaming(name=activity_name, url=stream_url)
    else:
        await interaction.response.send_message("Invalid activity type! Use 'playing', 'listening', 'watching', or 'streaming'.", ephemeral=True)
        return

    # Create the database table if it does not exist
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS activity_settings (
            guild_id INTEGER,
            activity_type TEXT,
            activity_name TEXT,
            stream_url TEXT,
            PRIMARY KEY(guild_id)
        )
    ''')

    # Only insert stream_url if the activity is 'streaming'
    if activity_type.lower() == "streaming":
        c.execute('''INSERT OR REPLACE INTO activity_settings (guild_id, activity_type, activity_name, stream_url) VALUES (?, ?, ?, ?)''', 
                  (interaction.guild.id, activity_type, activity_name, stream_url))
    else:
        c.execute('''INSERT OR REPLACE INTO activity_settings (guild_id, activity_type, activity_name, stream_url) VALUES (?, ?, ?, ?)''', 
                  (interaction.guild.id, activity_type, activity_name, None))  # Set stream_url to None for non-streaming activities
    conn.commit()
    conn.close()

    # Set the bot's activity while ensuring the status remains DND
    await bot.change_presence(status=discord.Status.dnd, activity=activity)
    await interaction.response.send_message(f"Bot activity changed to {activity_type} {activity_name}!", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="someone"),
        status=discord.Status.dnd  # Set the status to Do Not Disturb
    )
    await bot.tree.sync()

bot.run(TOKEN)
