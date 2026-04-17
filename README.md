# XTTS Voice Clone API

Projeto Docker para gerar audio a partir de texto usando um WAV de referencia com o modelo `xtts_v2`.

## O que faz
- Porta `3199`
- Usa GPU NVIDIA quando voce subir o servico `xtts-api-gpu`
- Usa CPU quando voce subir o servico `xtts-api-cpu`
- Endpoint HTTP simples para enviar `text`, `voz` e, opcionalmente, `speaker_wav`
- Usa `app/audio.wav` com `voz=m` e `app/feminina.wav` com `voz=f`
- Nao carrega o modelo no startup por padrao; defina `PRELOAD_MODEL=1` se quiser preload
- Idioma padrao: `pt`

## Licenca do modelo
O modelo `coqui/XTTS-v2` usa a **Coqui Public Model License**. Confira os termos antes de usar, principalmente em uso comercial.

## Subir com Docker Compose
### CPU
```bash
docker compose up -d xtts-api-cpu
```

### GPU
Requer Docker com suporte a NVIDIA.

```bash
docker compose up -d xtts-api-gpu
```

## Testar a API
### Health
```bash
curl http://localhost:3199/health
```

Com `PRELOAD_MODEL=0`, `loaded` fica `false` ate a primeira chamada em `/tts`.

### Gerar audio com WAV de referencia
```bash
curl -X POST http://localhost:3199/tts \
  -F "text=Ola Jone, este audio foi gerado com voz de referencia." \
  -F "speaker_wav=@referencia.wav" \
  --output saida.wav
```

### Gerar audio com voz masculina
```bash
curl -X POST http://localhost:3199/tts \
  -F "text=Ola Jone, este audio foi gerado com a voz masculina." \
  -F "voz=m" \
  --output saida.wav
```

### Gerar audio com voz feminina
```bash
curl -X POST http://localhost:3199/tts \
  -F "text=Ola Jone, este audio foi gerado com a voz feminina." \
  -F "voz=f" \
  --output saida.wav
```

## Endpoints
### `GET /`
Retorna status da API.

### `GET /health`
Retorna status, device e se o modelo foi carregado.

### `POST /tts`
Campos multipart:
- `text`: texto para falar
- `language`: idioma do texto, ex.: `pt`, `en`, `es`. Opcional; padrao `pt`
- `voz`: `m` para `app/audio.wav` ou `f` para `app/feminina.wav`. Opcional; padrao `m`
- `speaker_wav`: arquivo de referencia da voz. Opcional; se enviado, tem prioridade sobre `voz`

Resposta:
- arquivo WAV gerado

## Idiomas suportados pelo XTTS-v2
Exemplos comuns:
- `pt`
- `en`
- `es`
- `fr`
- `de`
- `it`
- `pl`
- `tr`
- `ru`
- `nl`
- `cs`
- `ar`
- `zh-cn`
- `ja`
- `hu`
- `ko`
- `hi`

## Observacoes
- Na primeira execucao o container vai baixar o modelo, entao demora mais.
- O WAV de referencia deve ter voz limpa, sem musica, sem eco e de preferencia uma unica pessoa falando.
- O servico GPU e CPU usam a mesma porta 3199. Suba apenas um dos dois.


curl -X POST http://localhost:3199/tts \
  -F "text=Olá Jone, este áudio foi gerado com voz de referência." \
  -F "language=pt" \
  -F "speaker_wav=@referencia.wav" \
  --output saida.wav

curl -X POST http://177.73.186.237:3199/tts \
  -F "text=Ola Jone, este audio foi gerado com a voz padrao." \
  -F "language=pt" \
  --output saida.wav
