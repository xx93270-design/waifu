
# Waifu Catch Bot

Telegram waifu-catch bot with:

- waifu management by ID
- group assignment for waifus
- event-based waifu pools
- rarity tiers from the provided spec
- private admin panel
- Railway-ready PostgreSQL deployment

## Environment variables

- `BOT_TOKEN` — Telegram bot token
- `DATABASE_URL` — PostgreSQL connection string
- `GOD_ADMIN_ID` — your Telegram numeric user ID
- `WEBHOOK_URL` — optional, for webhook mode
- `BOT_USERNAME` — optional, for gallery captions

## Main admin commands

- `/panel`
- `/addwaifu`
- `/waifuinfo <id>`
- `/waifuedit <id> <field> <value>`
- `/removewaifu <id>`
- `/group`
- `/event`
- `/settings`
- `/addgroup <chat_id|@username|link>`
- `/addadmin <user_id> <@username>`
- `/removeadmin <user_id>`
- `/broadcast <text>`

## Event commands

- `/event list`
- `/event info <event_id>`
- `/event create "Name" type group_id trigger_messages [description]`
- `/event toggle <event_id> on|off`
- `/event set <event_id> field value`
- `/event addwaifu <event_id> <waifu_db_id> <price> [weight]`
- `/event rmwaifu <event_id> <waifu_db_id>`

## Waifu edit fields

- `name`
- `anime`
- `rarity`
- `file_id`
- `price`
- `group_id`
- `event_id`
- `is_active`
