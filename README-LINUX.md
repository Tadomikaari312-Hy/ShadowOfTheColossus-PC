# Shadow of the Colossus — Linux build

Build pessoal do port nativo de **Shadow of the Colossus** (PS4, CUSA08809) com foco em
**Linux**. O jogo continua rodando a partir do **seu dump**; nada do jogo, da Sony ou da
Bluepoint é distribuído aqui.

Esta branch é baseada na linha `v0.57-opt8` do port e reúne as mudanças que eu uso no dia a
dia: launcher GTK4, FSR 3, fast-bind de descritores, correções de build Linux e ajustes de
desempenho. O `main` do fork continua limpo, apontando para o upstream, para receber PRs.

## O que tem nesta build

- **Launcher Linux** em GTK4/libadwaita (`launcher/sotc-launcher.sh`): pasta do jogo, saves,
  imagem, controles, opções de desempenho e diagnóstico.
- **FSR 3.1.6 Frame Generation** (`SOTC_FRAMEGEN=fsr` ou `auto`; **F8** liga/desliga): 30 FPS
  do jogo viram até 60 apresentações por segundo. Experimental; precisa de Vulkan 1.3 com
  imagens de armazenamento.
- **Fast bind de descritores** (ligado por padrão; `SOTC_FAST_BIND=0` desliga): reaproveita os
  binds quando o desenho seguinte usa o mesmo pipeline, push constants e recursos. Medido no
  Santuário: **24–25 → 29,6–30 FPS**, com o frametime em 33,3 ms.
- **Correções de build Linux** e dependências vendorizadas em `gpu/third_party/` (Boost,
  robin-map, VMA e Zydis), para não depender de pacotes que não existem em todas as distros.
- **Modo 60 FPS** e **modo PS4 Pro** do port original, além das opções de saída/upscaler.
- O launcher e os scripts Windows continuam no repositório, mas o foco desta branch é Linux.

O fast-bind também foi enviado ao upstream no PR
[#232](https://github.com/AjncSystem/ShadowOfTheColossus-PC/pull/232).

## Requisitos

- Linux 64-bit com driver **Vulkan 1.3** (Mesa/RADV, NVIDIA ou Intel).
- Um dump do jogo **CUSA08809** (EU 1.01 de preferência).
- Para som, os módulos `libSceNgs2.sprx` e `libSceUlt.sprx` extraídos do **seu** PS4.
- Para compilar: `clang` (ou GCC), `cmake`, `ninja`, `pkgconf`, headers do Vulkan, SDL3,
  `xxhash` e `glslang`.
- Para o launcher: `python3`, `python-gobject`, GTK4 e libadwaita.
- Opcional: `mangohud` para o overlay de desempenho.

No CachyOS/Arch, o básico é:

```bash
sudo pacman -S --needed base-devel clang cmake ninja pkgconf \
    vulkan-icd-loader vulkan-headers sdl3 xxhash glslang \
    python python-gobject gtk4 libadwaita mangohud git
```

Instale também o driver Vulkan da sua placa (`vulkan-radeon`, `vulkan-intel` ou
`nvidia-utils`). O Boost, o robin-map, o VMA e o Zydis já estão vendorizados; não precisa
instalá-los.

## Compilar

```bash
git clone https://github.com/Tadomikaari312-Hy/ShadowOfTheColossus-PC.git
cd ShadowOfTheColossus-PC
git submodule update --init --recursive
BB_PGO=off BB_LTO=ON bash build.sh
```

O binário fica em `out/bb-probe` e a biblioteca Vulkan em `out/gpu/libbbgpu.so`.
Para compilar mais rápido, use `BB_LTO=OFF`.

## Rodar

Pelo launcher:

```bash
./launcher/sotc-launcher.sh
```

Ou direto, mantendo saves e caches dentro de `user/`:

```bash
BB_PREBUILT=1 bash run-portable.sh
```

Na primeira execução, escolha a pasta do dump e os módulos de som no launcher. Os saves e o
cache de shaders ficam em `user/`.

### Variáveis úteis

| Variável | Efeito |
|---|---|
| `SOTC_FRAMEGEN=fsr` / `auto` | liga o FSR 3 ao iniciar (F8 alterna) |
| `SOTC_FAST_BIND=0` | desliga o fast bind (ligado por padrão) |
| `SOTC_FPS=1` | taxa de quadros e acerto do fast bind a cada 5 s |
| `SOTC_MANGOHUD=0` | não carrega o MangoHud |
| `SOTC_GAME_DIR=...` | pasta do dump CUSA08809 |
| `SOTC_SYS_MODULES=...` | pasta com `libSceNgs2.sprx` e `libSceUlt.sprx` |

## Resultados de teste

Hardware desta build: **Intel Xeon E5-2667 v4**, **31 GB RAM**, **AMD Radeon RX 6600M**
(Mesa RADV), CachyOS, 1080p. São medições deste PC; o upstream usa hardware diferente.

| Teste | Antes | Depois |
|---|---|---|
| Santuário (fast bind OFF → ON) | 24,0–25,0 FPS | **29,6–30,0 FPS** |
| `draw busy` no Santuário | 39–40 ms | **32,5–33,1 ms** |
| `parse` no Santuário | 22–23 ms | **18–20 ms** |
| Rota Santuário → 1º colosso | — | **30 FPS travados**, frametime 33,2–33,5 ms |

A rota até o primeiro colosso ficou em 30 FPS (limite do jogo), sem artefatos de textura ou
sombra observados com o fast bind. O FSR 3 apresentou 30 FPS do jogo como ~60 quadros/s.

## Estado

- Primeira visita a uma área ainda compila shaders e pode engasgar.
- O modo 60 FPS e o FSR 3 são experimentais; se algo quebrar, rode com
  `SOTC_FRAMEGEN=off SOTC_FPS=60` e compare.

## Créditos e licença

- [AjncSystem](https://github.com/AjncSystem/ShadowOfTheColossus-PC): upstream principal do port
  e mantenedor do repositório.
- [Oussama268](https://github.com/Oussama268/ShadowOfTheColossus-PC): releases `opt5`–`opt8`,
  correções de AMD/Intel, widescreen, 60 FPS e base de desempenho.
- [shadPS4](https://github.com/shadps4-emu/shadPS4) e o fork shadPS4 SotC: núcleo de vídeo Vulkan.
- [Pink-shadPS4](https://github.com/luizgustavs/Pink-shadPS4) (luizgustavs): cvars, heap guard,
  comandos em thread própria e correções de shader.
- [bloodborne_pc](https://github.com/Supermedo/bloodborne_pc): carregador, runtime nativo e
  launcher original.

O código segue a licença do repositório original (GPL-2.0-or-later). Nenhum arquivo do jogo,
firmware da Sony, save ou dump é incluído.
