# 🎧 Playlist Lab

**Aplicação de recomendação musical desenvolvida com Python, Flask, HTML, CSS e JavaScript, utilizando dados e características de áudio para gerar playlists personalizadas.**

**O projeto permite buscar uma música de referência e gerar recomendações a partir de padrões de escuta, características sonoras ou uma combinação dos dois, com diferentes opções de configuração e controle sobre os resultados.**

## Live Demo

🌐 https://playlists-edi5.onrender.com/

## Funcionalidades

- Busca de músicas no Spotify
- Geração de recomendações a partir de uma música de referência
- Modo **Listening**, baseado em padrões de escuta
- Modo **Sound**, baseado em características sonoras
- Modo **Hybrid**, combinando os dois métodos
- Ajuste dos pesos das características de áudio
- Ajuste do equilíbrio entre similaridade de escuta e sonora
- Controle de diversidade de artistas
- Ranking de músicas por similaridade ponderada
- Pontuações de escuta, som e compatibilidade geral
- Comparação de tempo considerando relações de half-time e double-time
- Player integrado do Spotify
- Remoção individual de músicas da playlist
- Regeneração de recomendações com diferentes configurações
- Autenticação com Spotify OAuth
- Atualização automática do access token
- Salvamento de playlists diretamente no Spotify
- Verificação da criação da playlist
- Layout responsivo
- Estados de carregamento e tratamento de erros

## Tecnologias

- Python
- Flask
- HTML5
- CSS3
- JavaScript
- Spotify Web API

## Como o projeto funciona

**O sistema parte de uma música de referência e busca faixas candidatas para gerar as recomendações.**

**No modo Listening, as músicas são avaliadas a partir de relações de escuta e comportamento dos usuários.**

**No modo Sound, as faixas são comparadas utilizando características como tempo, energia, valência, dançabilidade, acústica e instrumentalidade.**

**No modo Hybrid, os dois tipos de similaridade são combinados de acordo com o equilíbrio definido pelo usuário.**

**Após o cálculo das pontuações, as músicas são ordenadas por similaridade e passam por um controle de diversidade de artistas antes da formação da playlist final.**

## Fluxo de recomendação

```text
Música de referência
        │
        ▼
Busca de músicas candidatas
        │
        ├─────────────────┐
        ▼                 ▼
Padrões de escuta    Características sonoras
        │                 │
        ▼                 ▼
Pontuação de escuta   Pontuação sonora
        │                 │
        └────────┬────────┘
                 ▼
        Ranking de similaridade
                 │
                 ▼
        Diversidade de artistas
                 │
                 ▼
       Playlist recomendada
```

## Como executar

### 1. Clone o repositório

```bash
git clone https://github.com/anaclrsnts/playlist-engine.git
cd playlist-engine
```

### 2. Crie um ambiente virtual

**No Windows:**

```bash
python -m venv .venv
.venv\Scripts\activate
```

**No macOS ou Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure as credenciais do Spotify

**Crie um arquivo `.env` na raiz do projeto e adicione as credenciais da aplicação do Spotify:**

```env
SPOTIFY_CLIENT_ID=seu_client_id
SPOTIFY_CLIENT_SECRET=seu_client_secret
SPOTIFY_REDIRECT_URI=sua_redirect_uri
```

### 5. Execute o projeto

```bash
python app.py
```

**Abra no navegador:**

```text
http://127.0.0.1:5000
```

## Estrutura

```text
├── app.py
├── audio_features.py
├── recco_engine.py
├── requirements-audio.txt
├── vibe_engine.py
├── requirements.txt
├── README.md
├── .env
├── scripts
│   └── analyze_audio.py
├── templates/
│   └── index.html
└── static/
    ├── css/
    │   └── styles.css
    └── js/
        └── app.js
```

## Como o projeto funciona

- **Flask** gerencia a aplicação e as rotas do projeto.
- **Spotify Web API** fornece informações sobre músicas, artistas e dados utilizados nas recomendações.
- **Python** realiza os cálculos de similaridade e o ranking das músicas.
- **JavaScript** controla a interação com a interface e as requisições à aplicação.
- **HTML e CSS** estruturam e estilizam a interface.
- **Spotify OAuth** permite autenticar o usuário e salvar playlists diretamente em sua conta.

## Autora

**Ana Clara dos Santos**