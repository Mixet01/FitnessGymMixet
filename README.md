# Spese Mixet

PWA per tracciare spese ed entrate con:

- login Google OAuth
- database Supabase Postgres
- categorie personalizzabili per utente
- dashboard mensile con riepiloghi, trend e breakdown per categoria
- installazione come app su telefono o desktop

## Stack

- backend: Flask
- auth: Google Identity Services + verifica token lato server
- database: Supabase Postgres tramite `DATABASE_URL`
- frontend: HTML, CSS e JavaScript vanilla

## Avvio locale

1. Installa le dipendenze:

   ```powershell
   python -m pip install -r requirements.txt
   ```

2. Configura le variabili ambiente:

   ```powershell
   $env:GOOGLE_CLIENT_ID="IL_TUO_CLIENT_ID_GOOGLE"
   $env:DATABASE_URL="postgresql://postgres.xxx:[PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require"
   $env:SPESE_MIXET_SECRET="una-chiave-lunga-casuale"
   ```

   Opzionali:

   ```powershell
   $env:PWA_APP_NAME="Spese Mixet"
   $env:PWA_SHORT_NAME="Mixet"
   $env:PWA_THEME_COLOR="#1f7a6f"
   $env:PWA_BG_COLOR="#f7f1e8"
   $env:PWA_ICON_FILE="pwa-icon.png"
   $env:PWA_PORT="8010"
   $env:SPESE_MIXET_SESSION_DAYS="90"
   $env:ENABLE_BANKING_APP_ID="UUID_APP_ENABLE_BANKING"
   $env:ENABLE_BANKING_PRIVATE_KEY_PATH="C:\percorso\alla\chiave.pem"
   ```

3. Avvia il server:

   ```powershell
   python spese_mixet.py
   ```

4. Apri l'app:

   - locale: `http://127.0.0.1:8010`
   - stessa rete: `http://IP_DEL_PC:8010`

## Configurazione Google OAuth

Per il pulsante Google basta creare un client OAuth Web su Google Cloud e aggiungere tra gli `Authorized JavaScript origins` gli URL dove userai l'app, ad esempio:

- `http://127.0.0.1:8010`
- `http://localhost:8010`
- il dominio del deploy

Lato server serve solo `GOOGLE_CLIENT_ID` per verificare il token ricevuto dal client.

## Configurazione Supabase

1. Crea un progetto su Supabase.
2. Vai in `Project Settings -> Database`.
3. Copia la connection string Postgres.
4. Impostala in `DATABASE_URL`.

All'avvio l'app crea automaticamente queste tabelle:

- `app_users`
- `expense_categories`
- `expense_entries`

## Modalita fallback

Se `DATABASE_URL` non e impostata, l'app salva i dati in un file locale `data/spese_mixet.json`. E utile per sviluppo veloce, ma la modalita consigliata resta Supabase.

## Deploy

### Render

- Build command:

  ```text
  pip install -r requirements.txt
  ```

- Start command:

  ```text
  gunicorn spese_mixet:app --bind 0.0.0.0:$PORT
  ```

Variabili ambiente consigliate:

- `DATABASE_URL`
- `GOOGLE_CLIENT_ID`
- `SPESE_MIXET_SECRET`
- `PWA_APP_NAME`
- `PWA_SHORT_NAME`
- `PWA_THEME_COLOR`
- `PWA_BG_COLOR`

## Funzioni principali

- movimenti di tipo `spesa` o `entrata`
- categoria opzionale per ogni movimento
- categorie modificabili e archiviabili
- insight mensili con saldo, spesa media, categoria top e andamento ultimi 6 mesi
- export CSV del mese selezionato
- PWA installabile con cache della shell applicativa

## Icona personalizzata

Puoi usare una tua icona senza cambiare codice.

Opzione piu semplice:

1. metti il file dentro `static/`
2. chiamalo ad esempio `pwa-icon.png`
3. riavvia l'app

Opzione esplicita con variabile ambiente:

```powershell
$env:PWA_ICON_FILE="mia-icona.png"
```

Formati supportati:

- `.png`
- `.jpg`
- `.jpeg`
- `.svg`

Se non imposti nulla, l'app prova in automatico questi nomi dentro `static/`:

- `pwa-icon.png`
- `pwa-icon-512.png`
- `pwa-icon.jpg`
- `pwa-icon.jpeg`
- `pwa-icon.svg`
- `icon.png`
- `icon.jpg`
- `icon.jpeg`
- `icon.svg`

Se non trova nessun file, usa l'icona SVG generata di default.

## Sync Postepay

Il collegamento automatico con saldo e movimenti Postepay non passa da scraping o login diretto nel sito Poste. La strada corretta e conforme e usare un provider Open Banking / PSD2 autorizzato.

Questa app usa il flusso ufficiale di `Enable Banking` come aggregatore PSD2:

1. crea o attiva un'app in Enable Banking
2. scarica la chiave privata `.pem`
3. whitelista l'URL di callback dell'app, ad esempio:

   - `http://127.0.0.1:8010/auth/enable-banking/callback`
   - `http://localhost:8010/auth/enable-banking/callback`

4. configura almeno queste variabili:

   ```powershell
   $env:ENABLE_BANKING_APP_ID="UUID_APP_ENABLE_BANKING"
   $env:ENABLE_BANKING_PRIVATE_KEY_PATH="C:\percorso\alla\chiave.pem"
   ```

Opzionali:

```powershell
$env:ENABLE_BANKING_BASE_URL="https://api.enablebanking.com"
$env:ENABLE_BANKING_COUNTRY="IT"
$env:ENABLE_BANKING_ASPSP_MATCH="postepay,poste italiane,poste"
$env:ENABLE_BANKING_CONSENT_DAYS="90"
$env:ENABLE_BANKING_TX_DAYS="90"
```

Nell'app trovi poi:

- `Collega Postepay` per aprire il consenso PSD2
- `Aggiorna saldo` per scaricare saldo e movimenti recenti
- `Scollega` per rimuovere il collegamento e la cache bancaria locale

Fonti ufficiali utili:

- Poste Italiane espone BancoPosta e Postepay alle Terze Parti PSD2 tramite CBI Globe
- la pagina Open Banking di Poste indica che una Terza Parte autorizzata puo accedere alle informazioni di Conto BancoPosta e Carta Postepay previo consenso

Una strada concreta da valutare e un provider come Enable Banking, che nel changelog dell'8 aprile 2026 dichiara supporto per Poste Italiane / Postepay su account personali e business.
