# Azure handoff for OpenClaw (from azure-lab, 2026-06-04)

Azure provisioning for this bot is done in the `~/projects/azure-lab` session. This file is the
handoff: what exists, how to wire it, what must change client-side. No secrets are stored here;
fetch keys live with the `az` commands below (the same machine's az login has access).

## Provisioned resources (resource group `openclaw-rg`)

| Resource | Region | Purpose |
|---|---|---|
| VM `openclaw-vm` (public IP <VM_PUBLIC_IP>) | southeastasia | bot host; SSH as `azureuser`, port 22 locked to a fixed IP |
| OpenAI account `<OAI_RESOURCE>` | swedencentral | chat + agent models |
| AIServices account `<AIS_RESOURCE>` | swedencentral | OCR model |

LLM is in swedencentral because southeastasia has zero deployable chat/vision quota for this
subscription. The VM (Singapore) calls the swedencentral endpoints over the internet (~190 ms,
fine for a receipt bot).

### SSH access (port 22 lock)

The NSG rule `default-allow-ssh` on `openclaw-vmNSG` allows SSH only from one source IP. As of
2026-06-04 it is locked to the VPN egress IP `<ADMIN_IP>/32`. To SSH in, connect to the same
VPN first; if your egress IP changes (VPN drop or rotation), re-point the rule:

```bash
RG=openclaw-rg; VM=openclaw-vm
NEWIP=$(curl -s -4 https://ifconfig.me)   # run while on the VPN
az network nsg rule update -g "$RG" --nsg-name "${VM}NSG" -n default-allow-ssh \
  --source-address-prefixes "${NEWIP}/32"
# To allow VPN + another IP at once, pass both: "<ADMIN_IP>/32" "<other-ip>/32"
```

## Model lineup, deployment name to role

| Deployment | Role |
|---|---|
| `gpt-5-mini` | default chat; xlsx + database toolset agent; pptx toolset agent |
| `o4-mini` | reasoning escalation for hard analytics |
| `mistral-document-ai-2512` | receipt OCR (standby fallback for the OCR gate; not wired as a chat provider) |

## .env (fetch values live, never commit)

Run this; paste the output into `.env` (gitignored):

```bash
RG=openclaw-rg
# Provider 1: chat + agents (OpenAI v1 surface)
echo "AZURE_OPENAI_BASE_URL=$(az cognitiveservices account show -g $RG -n <OAI_RESOURCE> --query properties.endpoint -o tsv)openai/v1/"
echo "AZURE_OPENAI_API_KEY=$(az cognitiveservices account keys list -g $RG -n <OAI_RESOURCE> --query key1 -o tsv)"
# Provider 2: OCR (AIServices / Foundry surface)
echo "AZURE_AI_FOUNDRY_ENDPOINT=$(az cognitiveservices account show -g $RG -n <AIS_RESOURCE> --query properties.endpoint -o tsv)"
echo "AZURE_AI_FOUNDRY_API_KEY=$(az cognitiveservices account keys list -g $RG -n <AIS_RESOURCE> --query key1 -o tsv)"
# SSH deploy target
echo "VM_HOST=<VM_PUBLIC_IP>   # azureuser"
```

## openclaw.json

- One chat provider: `azure-oai` on the OpenAI v1 base URL, serving `gpt-5-mini` (default chat
  plus inline vision OCR) and `o4-mini` (reasoning escalation). Model refs by deployment name:
  `azure-oai/gpt-5-mini`, `azure-oai/o4-mini`. Drop the old `gpt-4o-mini` / `gpt-4o` refs.
- Mistral Document AI is NOT an OpenClaw provider. It is a dedicated Foundry OCR API
  (`POST {AZURE_AI_FOUNDRY_ENDPOINT}providers/mistral/azure/ocr`, Bearer auth), not
  chat-completions, so the agent cannot select it as a model. It stays provisioned only as a
  standby fallback for the OCR gate (`scripts/ocr_test/`) if gpt-5-mini underperforms.

## Required client changes (gpt-5-mini is reasoning-family, or requests 400)

Detail in `gpt-5-mini-handoff.md`. Summary: use `max_completion_tokens` (not `max_tokens`);
remove `temperature` / `top_p` / penalties; set `parallel_tool_calls: false` when using a
json_schema `response_format`; tune `reasoning_effort` per role (chat `low`, agents `medium`).

## Tasks for this session

- [ ] Populate `.env` from the fetch commands above.
- [ ] Update `openclaw.sample.json` / `openclaw.json`: two providers, new model refs.
- [ ] Apply the gpt-5-mini request-format fixes in the client.
- [ ] Wire the OCR path to the Foundry / `mistral-document-ai-2512` surface.
- [ ] Deploy on the VM (`docker compose up -d --build`) and verify with a real receipt.

Capability detail: `gpt-5-mini-openclaw-fit.md`. Azure teardown when done is one command in the
azure-lab session: `az group delete -n openclaw-rg`.
