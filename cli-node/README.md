# @startanaicompany/rolez

Agent-side CLI for the [rolez](https://github.com/Ryan-SAAS/rolez) role
registry + provisioner at startanaicompany.com.

## Install

```bash
npm install -g @startanaicompany/rolez
```

Or as a one-off:

```bash
npx -p @startanaicompany/rolez rolez list
```

## Env

```
ROLEZ_API_URL                  e.g. https://rolez.startanaicompany.com
ROLEZ_API_KEY                  the assistant's tech.saac MCP api key
                               (also accepts MCP_ORCHESTRATOR_API_KEY for parity
                                with @startanaicompany/techsaac-cli)
```

## Commands

```bash
rolez list [--tag X] [--kind agent|assistant] [--json]
rolez search <query> [--json]
rolez show <slug>[@version]
rolez inspect <slug>[@version]
rolez provision <slug> --org <id> --product <id> --name <name> \
  [--version <v>] [--var KEY=value]... [--skill name@version]... \
  [--subagent name@version]... [--binding catalog=connection_id]...
```

Lifecycle commands (`start|stop|restart|send`) live in
[`@startanaicompany/techsaac-cli`](https://www.npmjs.com/package/@startanaicompany/techsaac-cli) —
rolez handles the create/instantiate path only.

## Exit codes

```
0 ok      1 usage      2 auth      3 not found      4 network      5 client error
```
