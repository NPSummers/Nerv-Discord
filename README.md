# Nerv-Discord

Reusable Discord client written in Nerv, using the language's native HTTPS, JSON, and WebSocket runtime. The sibling `Nerv-Bot` demonstrates guild `/ping` registration and Gateway interactions. The compiler is in `../Nerv-v2`.

## Use

```toml
[dependencies]
discord = { path = "../Nerv-Discord" }
```

```nerv
import discord

fn on_command(interaction: Json) -> string
    if json_i64(discord_field(interaction, "type"), 0) == 2
        "Hello!"
    else
        ""

fn on_gateway(handle: i64, kind: string, text: string, bytes: []u8, state: string) -> []string
    discord_handle(handle, kind, text, bytes, state, on_command)
```

Call `discord_run(token, intents, on_gateway)` to discover and connect to the Gateway. The command callback returns response content, or an empty string to ignore an interaction. Keep callbacks short. The SDK sends a type-4 response; it does not automatically defer long work. Configuration is passed explicitly; this library never reads `.env`.

`discord_register_command(token, application_id, guild_id, discord_command(name, description))` registers one guild slash command. IDs remain strings. `discord_request`, registration, response, and connection functions return ordinary `Result` values. `DiscordError` contains a secret-free `message`, HTTP `status` (zero for non-HTTP errors), and `retry_ms` for 429 responses. Successful empty HTTP bodies become JSON null.

The current compiler supports qualified module references; unique unqualified references remain compatible. SDK declarations retain `discord_` prefixes for compatibility. `discord_step` is the deterministic Gateway state transition used by the transport adapter. Callback state contains the bot token and session information: never print or persist it in logs.

## Behavior

API v10, uncompressed JSON, Identify/Resume, Dispatch sequence tracking, Hello jitter, periodic/requested heartbeats, ACK detection, reconnect requests, invalid sessions, and fatal close classification are implemented. Heartbeat deadlines are checked on busy and idle events. Outbound Gateway messages are limited to 4096 bytes. Missing Hello times out after ten seconds. Production REST/Gateway connections use HTTPS/WSS with normal certificate validation.

Retries back off and stop after eight connections; Identify attempts also respect the discovered remaining session-start budget. General REST bucket queues, automatic REST retries, sharding, full model coverage/cache, deferred interactions/follow-ups, voice, and compression are not implemented. A 429 is returned to the caller with its retry delay; the SDK does not sleep in a Gateway callback. The synchronous runtime can delay heartbeats during HTTP calls. See the bot README for deployment/configuration instructions and the handoff for runtime memory limits.

## Verification

From this folder, using the freshly built sibling compiler:

```powershell
$compiler = '..\Nerv-v2\target\debug\nerv.exe'
& $compiler check --locked
& $compiler test --locked
& $compiler fmt --check
& $compiler build --manifest-path tools/mock-client/Nerv.toml --locked
python tools/mock_test.py tools/mock-client/target/nerv/debug/discord_mock_client.exe
& $compiler build --release --manifest-path tools/mock-client/Nerv.toml --locked
python tools/mock_test.py tools/mock-client/target/nerv/release/discord_mock_client.exe
```

Python is used only to run local mock peers during development. The library and bot run entirely as native Nerv code. Mock tests exercise Identify -> READY -> heartbeat/ACK -> reconnect -> Resume -> fatal close and HTTP status handling (200/401/403/429/503). REST mocks exercise transport, command payloads, and response classification; production Discord registration and interaction endpoints require live validation. Source tests also cover missed ACKs, malformed JSON, invalid sessions, JSON escaping, and secret-free errors. No live Discord test has been performed.

Protocol references: [Gateway](https://docs.discord.com/developers/events/gateway), [opcodes and close codes](https://docs.discord.com/developers/topics/opcodes-and-status-codes), [application commands](https://docs.discord.com/developers/interactions/application-commands), [interaction responses](https://docs.discord.com/developers/interactions/receiving-and-responding), [rate limits](https://docs.discord.com/developers/topics/rate-limits).
