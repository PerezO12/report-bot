# BotDaily v2 - Recent Changes & Fixes

## Fixed: Dynamic Option Loading in Callback Handlers (2026-05-22)

### Problem
When users selected an option (region, module, priority, APK) and advanced to the next step, the dynamic options from the database were not appearing. Only hardcoded options showed up.

### Root Cause
The `_handle_callback_step()` function was directly calling `context.bot.send_message()` to display the next question, bypassing the dynamic option loading logic in `_send_question()`.

### Solution Implemented

#### 1. Enhanced `_send_question()` Function
- Added optional `chat_id` parameter to support both message and callback contexts
- When `chat_id` is provided (callback context), uses `context.bot.send_message()`
- When `chat_id` is None (message context), uses `update.effective_message.reply_text()`
- Dynamic option loading now works in all contexts

#### 2. Updated Step Handlers
All step handlers now call `_send_question()` when advancing to the next step:
- **`_handle_callback_step()`** - Options steps (region, module, priority, apk, boolean)
- **`_handle_date_selector_step()`** - Daily date selection
- **`_handle_text_step()`** - Text input steps
- **`_handle_photo_step()`** and **`_handle_media_step()`** - Media steps

#### 3. Database Verification
Confirmed database contains:
- **22 Modules** including "Otro" (custom input option)
- **6 Priority Levels** including "Extremadamente urgente"
- **7 APKs** including "Otro" (custom input option)

### Verification

Test dynamic option loading:
```bash
cd e:\BotDaily
python -c "
import asyncio
from bot.database import init_db
from bot.conversation import _load_dynamic_options

async def test():
    db = await init_db('botdaily.db')
    modules = await _load_dynamic_options('step_module', db)
    print(f'Loaded {len(modules)} modules')
    await db.close()

asyncio.run(test())
"
```

Expected output:
```
Loaded 22 modules
```

### How to Test Manually

1. Start the bot: `python main.py`
2. Open Telegram bot
3. Send `/incidencia` command
4. At each step with dynamic options:
   - Region selection → Shows Región 0-4
   - Module selection → Shows 21 modules + "Otro" button
   - Priority selection → Shows 6 priority levels including "Extremadamente urgente"
5. Send `/solicitud` command
   - APK selection → Shows 6 APKs + "Otro" button
   - Priority selection → Shows 6 priority levels

### Files Modified

- `bot/conversation.py`:
  - Enhanced `_send_question()` with `chat_id` parameter
  - Updated all step handlers to use `_send_question()` for next step
  - Added logging for dynamic option loading

### Notes for Future Development

- "Otro" option selected but custom input handling not yet implemented (planned for future)
- Database seeding works correctly with INSERT OR IGNORE to avoid duplicates
- All flows now properly load options from database when database is available
