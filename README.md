# Shadow of the Colossus — PC (Linux build)

**Este fork é focado em Linux.** Launcher GTK4, FSR 3, fast bind, correções de build e
instruções completas estão em **[README-LINUX.md](README-LINUX.md)**. As seções abaixo são do
port original para Windows e ficam como referência.

**[Português](#português)** · **[English](#english)** · [Linux](README-LINUX.md) · [Releases](../../releases) · [Changelog](CHANGELOG.md)

> **Nenhum arquivo do jogo nem da Sony está incluído / No game or Sony files are included.**
> Você precisa do seu próprio dump do jogo e, para ter som, de dois módulos do seu próprio
> console. / You need your own game dump and, for sound, two modules from your own console.
> Este projeto não tem ligação com a Sony Interactive Entertainment nem com a Bluepoint Games. /
> This project is not affiliated with Sony Interactive Entertainment or Bluepoint Games.

---

## Português

Port nativo do **Shadow of the Colossus** de PS4 (Bluepoint, 2018; CUSA08809, versão EU 1.01)
para **Linux**. O código x86-64 do próprio jogo roda direto na CPU do PC e a GPU do PS4
é traduzida para Vulkan. Não é um emulador completo: é um carregador com as funções de sistema
de que o jogo precisa, no estilo do [bloodborne_pc](https://github.com/Supermedo/bloodborne_pc).

### Novidades

- **Novo nesta build:** fast bind de descritores (ligado por padrão; `SOTC_FAST_BIND=0` desliga),
  FSR 3.1.6 com F8, launcher GTK4 e correções de build Linux. No Santuário: 24–25 → 29,6–30 FPS.
- **Base:** todas as atualizações até a **0.57-opt8** do Oussama, mais as otimizações locais e o
  launcher Linux. Detalhes e medições no [CHANGELOG](CHANGELOG.md) e no [README-LINUX](README-LINUX.md).

Detalhes de cada versão no [CHANGELOG](CHANGELOG.md).

### Problemas conhecidos

- Na primeira abertura depois de atualizar, os shaders são compilados de novo: o primeiro
  carregamento demora e engasga.
- Placas **AMD**: a correção das cores verdes/rosas ([#7](../../issues/7)) foi testada nesta
  build numa RX 6600M. Se ainda aparecer, mande o seu `user/last_run.log` na issue.
- Com 8 GB de memória de vídeo, o uso fica perto do limite em áreas grandes.

### Download e uso

1. Baixe o `SotC-PC.zip` da página [Releases](../../releases) e descompacte numa pasta.
2. Abra o **`SotC.exe`**. Na primeira vez o lançador procura sozinho, nos discos do PC:
   - a pasta do jogo (o dump CUSA08809, com `eboot.bin`, `sce_module` e `sce_sys`);
   - os módulos de som (`libSceNgs2.sprx` e `libSceUlt.sprx`) de um shadPS4 que você já
     tenha, na pasta `user/sys_modules`, e copia para a pasta de dados do port;
   - um save do jogo no shadPS4, que ele oferece importar;
   - as DLCs do jogo, se houver: a pasta `addcont` do shadPS4, ou uma pasta com uma subpasta por DLC.
     Também dá para escolher em **Jogo e saves > Pasta de DLC**.
3. Confira a página **Jogo e saves**. A **biblioteca de jogos** funciona como a do shadPS4:
   adicione as pastas dos seus jogos e escolha o jogo na lista.
4. Clique em **JOGAR**.

Requisitos: Windows 10/11 64-bit, placa de vídeo com **Vulkan 1.3** (NVIDIA, AMD ou Intel
com driver recente). Não precisa instalar Python.

#### Os arquivos que você precisa ter

| O quê | De onde | Para quê |
|---|---|---|
| Dump do jogo CUSA08809 (EU 1.01 de preferência) | o seu PS4, pelo GoldHEN | o jogo |
| `libSceNgs2.sprx`, `libSceUlt.sprx` decriptados | o seu PS4 (`/system/common/lib/`, FTP do GoldHEN), ou o `user/sys_modules` do shadPS4 | som (sem eles o jogo roda mudo) |

Os modos de patch (60 FPS, filtro 16x) só valem para a versão EU 1.01; nas outras o jogo roda
normalmente, a 30 FPS.

### O lançador

- **Jogar:** confere a versão do jogo, o som, os saves e a placa de vídeo antes de abrir;
  opções rápidas de saída, upscaler, 60 FPS, filtro 16x e tela cheia.
- **Jogo e saves:** biblioteca de jogos, busca automática no PC, importação de saves do shadPS4.
- **Imagem e FPS:** saída 720p a 4K (o jogo renderiza em 1080p e o FSR 1 + RCAS amplia),
  modo PS4 Pro (o jogo oferece Cinematográfico/Desempenho no próprio menu), efeitos (vinheta,
  névoa, SSAO) e opções de desempenho.
- **Controles:** controle (DualShock 4, DualSense, Xbox) automático; câmera no mouse;
  **troca de teclas** clicando na ação e apertando a tecla nova.
- **Avançado:** cvars do motor Bluepoint, diagnóstico, atalho na área de trabalho (com o ícone
  do seu jogo). O registro de cada sessão fica em `user/last_run.log`.

### O que foi feito

| Área | Resultado |
|---|---|
| Boot | O jogo inicia com o carregador do bbport: imports por NID, fibras, patches de CPU (SSE4a), imagem abaixo de 2 GiB (o jogo guarda ponteiros em 31 bits). |
| Vídeo | Núcleo de vídeo do fork shadPS4 SotC dentro do port: logos, abertura, menus, campo aberto sem polígonos pretos, sombras com iluminação correta. |
| Texturas | Streaming de texturas (o jogo carrega os mips mais finos), sem corrupção de memória. |
| Água | Reflexos em espaço de tela, reflexos de ambiente por *probe*, respingos e anéis ao nadar. |
| Saves | Gravação, carregamento e exclusão pela lista de saves na tela. |
| Som | Áudio real com os módulos Ngs2/Ult do próprio usuário. |
| Controles | Teclado e controle juntos, câmera no mouse, troca de teclas no lançador. |
| Modos | 60 FPS (patch de illusion), filtro anisotrópico 16x, modo PS4 Pro, saída até 4K. |
| Desempenho | Nesta build (Xeon E5-2667 v4 + RX 6600M): Santuário **24–25 → 29,6–30 FPS** com fast bind; rota até o 1º colosso em **30 FPS**. No demo do upstream (i9 + RTX 2060 SUPER): **37–45 → ~67 FPS**; ponte do cânion **~17 → 29–34 FPS**. |

### Perguntas comuns

- **DirectX 11/12?** Não. O núcleo de vídeo traduz a GPU do PS4 para Vulkan (shaders em SPIR-V).
  Toda placa com DirectX 12 moderno também tem Vulkan 1.3: basta o driver atualizado.
- **AMD e Intel?** Quase todas as otimizações valem para qualquer placa. Duas só ligam
  sozinhas na NVIDIA: o envio periódico à GPU e as leituras antecipadas. Em **Imagem e FPS >
  Envio de trabalho à GPU**, escolha **Ligado** para usá-las numa AMD ou Intel. Se a tela ficar
  preta, volte para **Automático**.
- **Por que não vem o som pronto?** Os dois `.sprx` são firmware da Sony; distribuí-los não é
  permitido. O lançador acha e copia os seus automaticamente.
- **O jogo fechou sozinho.** Abra uma *issue* com o arquivo `user/last_run.log`.

---

## English

A native Windows port of the PS4 **Shadow of the Colossus** (Bluepoint, 2018; CUSA08809, EU 1.01)
for **Windows 10/11**. The game's own x86-64 code runs directly on the PC's CPU and the PS4 GPU
is translated to Vulkan. It is not a full emulator: it is a loader with the system functions the
game needs, in the style of [bloodborne_pc](https://github.com/Supermedo/bloodborne_pc).

### What's new

- **New in this build:** descriptor fast bind (on by default; `SOTC_FAST_BIND=0` disables it),
  FSR 3.1.6 with F8, GTK4 launcher and Linux build fixes. At the Sanctuary: 24–25 → 29.6–30 FPS.
- **Base:** all updates through Oussama's **0.57-opt8**, plus the local optimizations and the
  Linux launcher. Details and measurements in [CHANGELOG](CHANGELOG.md) and [README-LINUX](README-LINUX.md).

Full details in the [CHANGELOG](CHANGELOG.md) (in Portuguese).

### Known issues

- The first start after updating rebuilds the shaders: the first load is slow and stutters.
- **AMD** GPUs: the green/pink tint fix ([#7](../../issues/7)) was tested on an RX 6600M in this
  build. If it persists, attach your `user/last_run.log` to the issue.
- With 8 GB of video memory, usage gets close to the limit in large areas.

### Download and use

1. Download `SotC-PC.zip` from [Releases](../../releases) and unzip it into a folder.
2. Run **`SotC.exe`**. On first start the launcher searches the PC's drives for:
   - the game folder (the CUSA08809 dump with `eboot.bin`, `sce_module` and `sce_sys`);
   - the sound modules (`libSceNgs2.sprx` and `libSceUlt.sprx`) of an installed shadPS4
     (`user/sys_modules`), which it copies to the port's data folder;
   - a shadPS4 save of the game, which it offers to import;
   - the game's DLCs, if any (shadPS4's `addcont` folder, or a folder with one subfolder per DLC).
3. Check the **Game and saves** page. The **game library** works like shadPS4's.
4. Click **PLAY**.

Requirements: Windows 10/11 64-bit and a **Vulkan 1.3** GPU (NVIDIA, AMD or Intel with a recent
driver). No Python install needed.

| What | Where from | What for |
|---|---|---|
| CUSA08809 game dump (EU 1.01 preferred) | your PS4, through GoldHEN | the game |
| decrypted `libSceNgs2.sprx`, `libSceUlt.sprx` | your PS4 (`/system/common/lib/`, GoldHEN FTP), or shadPS4's `user/sys_modules` | sound (silent without them) |

The patch modes (60 FPS, 16x filtering) only apply to EU 1.01; other versions run at 30 FPS.

### Launcher features

Game library and automatic search, shadPS4 save import, 720p–4K output (the game renders at
1080p, upscaled with FSR 1 + RCAS), PS4 Pro mode, 60 FPS and 16x AF modes, controller support
(DualShock 4, DualSense, Xbox) with mouse camera, key remapping, Bluepoint engine cvars, desktop
shortcut and a session log in `user/last_run.log`.

This build (Xeon E5-2667 v4 + RX 6600M) runs the Sanctuary at **24–25 → 29.6–30 FPS** with
fast bind and the route to the first colossus at **30 FPS**. On the upstream hardware
(i9 + RTX 2060 SUPER), 60 FPS mode averages ~67 FPS, with 29–34 FPS in its heaviest section. Vulkan only (no DirectX). AMD and Intel can enable the
NVIDIA-only submission options under **Image and FPS > GPU work submission**.

**Why no sound files?** The two `.sprx` files are Sony firmware and may not be redistributed;
the launcher finds and copies yours automatically. **The game closed by itself?** Open an issue
with `user/last_run.log`.

---

## Compilar / Building

Windows com / with [MSYS2](https://www.msys2.org/) (CLANG64). Pacotes / packages:
[packaging/windows/README.md](packaging/windows/README.md). Para congelar o `SotC.exe` / to
freeze `SotC.exe`: um Python do Windows com PyInstaller e Pillow / a Windows Python with
PyInstaller and Pillow (`WINPYTHON`).

```
bash build.sh                              # out/bb-probe.exe
bash packaging/windows/package_sotc.sh     # dist/SotC-PC.zip
```

O empacotamento recusa qualquer `.sprx`/`.prx` / packaging refuses any `.sprx`/`.prx`: Sony
firmware never goes into the package. Ferramentas de teste / test tools: `tools/`. Variáveis de
diagnóstico / diagnostic variables: [docs/sotc/README-SotC.md](docs/sotc/README-SotC.md).

## Créditos / Credits

- [Tadomikaari312-Hy](https://github.com/Tadomikaari312-Hy/ShadowOfTheColossus-PC): build Linux,
  launcher GTK4, fast bind e medições desta branch.
- [AjncSystem](https://github.com/AjncSystem/ShadowOfTheColossus-PC): upstream principal e
  mantenedor do repositório.
- [Oussama268](https://github.com/Oussama268/ShadowOfTheColossus-PC): releases `opt5`–`opt8`,
  correções de AMD/Intel, widescreen, 60 FPS e base de desempenho.
- [bloodborne_pc](https://github.com/Supermedo/bloodborne_pc) (Supermedo, deadinside28 and
  forks): carregador, runtime nativo e lançador / loader, native runtime and launcher. README
  original: [docs/bbport](docs/bbport/README.md).
- [shadPS4](https://github.com/shadps4-emu/shadPS4) e o fork / and the shadPS4 SotC fork:
  núcleo de vídeo Vulkan / Vulkan video core.
- [Pink-shadPS4](https://github.com/luizgustavs/Pink-shadPS4) (luizgustavs): cvars de culling /
  culling cvars, BPE heap guard, envio periódico / periodic submission, gravador de comandos em
  thread própria / command recording thread, correções de shader / shader fixes (fetch-shader
  constants, `V_ALIGNBIT`, `V_CVT_PK_U8_F32`), tabelas de texturas indexadas / dynamic T# tables
  (`dynamic_tsharp_array_size`), a abordagem das estatísticas de LOD / the LOD statistics
  approach e o acesso direto à memória para o SotC / and direct memory access for SotC.
- Patch de 60 FPS / 60 FPS patch: illusion (GoldHEN cheats).

Licença / License: **GPL-2.0-or-later** ([LICENSE](LICENSE)).
