"""
Channel-aware tool filtering for the Hermes gateway.

Filters enabled toolsets based on message source (user_id, chat_type)
before they reach the AIAgent. This is hard enforcement — the model
literally cannot call tools that aren't in its function schema.

Config (config.yaml):

    discord:
      tool_permissions:
        owner_id: '273760138135863296'
        dm_owner:
          mode: full          # all tools
        dm_other:
          mode: restricted    # only safe_toolsets
          safe_toolsets:
            - clarify
            - web
            - skills
            - session_search
            - todo
        guild:
          mode: none           # zero tools — chat only
        guild_admin:
          mode: full           # optional: admin channels get full access
          channel_ids:
            - 'CHANNEL_ID_1'
"""

import logging
from typing import Optional, Set

logger = logging.getLogger(__name__)

# Default safe toolsets for non-owner DMs
DEFAULT_SAFE_TOOLSETS = {"clarify", "web", "skills", "session_search", "todo"}

# Toolsets that grant filesystem/terminal/memory access — never exposed to non-owners
_RESTRICTED_TOOLSETS = {
    "terminal", "file", "memory", "code_execution",
    "debugging", "homeassistant", "spotify",
}


def filter_toolsets_for_source(
    enabled_toolsets: Set[str],
    user_id: Optional[str],
    chat_type: str,  # "dm", "group", "channel", "thread"
    guild_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    config: Optional[dict] = None,
) -> Set[str]:
    """
    Filter enabled_toolsets based on who is talking and where.

    Returns the filtered set of toolset names. If no tool_permissions
    config is present, returns enabled_toolsets unchanged (backward-compatible).
    """
    if not config:
        return enabled_toolsets

    discord_cfg = config.get("discord") or {}
    perms = discord_cfg.get("tool_permissions")
    if not perms:
        return enabled_toolsets

    owner_id = str(perms.get("owner_id", ""))
    is_owner = user_id and str(user_id) == owner_id

    # Determine which rule applies
    if chat_type == "dm":
        if is_owner:
            rule = perms.get("dm_owner", {})
        else:
            rule = perms.get("dm_other", {})
    elif chat_type in ("channel", "thread"):
        # Check guild_admin channel override
        guild_admin = perms.get("guild_admin", {})
        admin_channels = {
            str(c) for c in (guild_admin.get("channel_ids") or [])
        }
        if is_owner and chat_id and str(chat_id) in admin_channels:
            rule = guild_admin
        elif is_owner:
            # Owner in guild channel — check if there's a specific owner guild rule
            rule = perms.get("guild_owner", perms.get("guild", {}))
        else:
            rule = perms.get("guild", {})
    elif chat_type == "group":
        if is_owner:
            rule = perms.get("group_owner", perms.get("guild", {}))
        else:
            rule = perms.get("guild", {})
    else:
        return enabled_toolsets

    mode = rule.get("mode", "full")

    if mode == "full":
        logger.debug("Tool filter: full access for user=%s chat_type=%s", user_id, chat_type)
        return enabled_toolsets

    elif mode == "none":
        logger.info("Tool filter: NO tools for user=%s chat_type=%s", user_id, chat_type)
        return set()

    elif mode == "restricted":
        safe = set(rule.get("safe_toolsets") or DEFAULT_SAFE_TOOLSETS)
        filtered = enabled_toolsets & safe
        logger.info(
            "Tool filter: restricted for user=%s chat_type=%s — %d/%d toolsets remain",
            user_id, chat_type, len(filtered), len(enabled_toolsets),
        )
        return filtered

    else:
        logger.warning("Tool filter: unknown mode '%s', passing through", mode)
        return enabled_toolsets
