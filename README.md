# Fitness Gym Mixet

PWA mobile per calcolare:

- `BMI`
- `BMR`
- `TDEE`
- `BF` con metodo `Navy` opzionale
- piano dieta con macro variabili e obiettivi opzionali
- storico piani e check-in peso/BF

L'app mantiene:

- login Google OAuth
- persistenza sessione
- database Supabase/Postgres tramite `DATABASE_URL`
- fallback locale in `data/fitness_mixet.json` se il DB non e configurato

## Stack

- backend: Flask
- auth: Google Identity Services + verifica token lato server
- database: Supabase Postgres
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
   $env:PWA_APP_NAME="Fitness Gym Mixet"
   $env:PWA_SHORT_NAME="Fitness Gym"
   $env:PWA_THEME_COLOR="#0f4c81"
   $env:PWA_BG_COLOR="#06111f"
   $env:PWA_ICON_FILE="pwa-icon.png"
   $env:PWA_PORT="8010"
   $env:SPESE_MIXET_SESSION_DAYS="90"
   ```

3. Avvia il server:

   ```powershell
   python spese_mixet.py
   ```

4. Apri l'app:

   - locale: `http://127.0.0.1:8010`
   - stessa rete: `http://IP_DEL_PC:8010`

## Database

Se `DATABASE_URL` e presente, l'app crea automaticamente queste tabelle:

- `app_users`
- `fitness_profiles`
- `fitness_plans`
- `fitness_checkins`

Se `DATABASE_URL` non e impostata, i dati vengono salvati in `data/fitness_mixet.json`.

## Formule usate

- `BMI`: peso / altezza^2
- `BMR`: formula di Mifflin-St Jeor
- `TDEE`: BMR moltiplicato per il fattore attivita
- `BF` automatico: stima da BMI, eta e sesso
- `BF` opzionale: metodo `Navy` con vita, collo e fianchi
- piano dieta: mantenimento, cut, cut aggressivo, bulk e bulk aggressivo

## Campi principali

Nella schermata calcolo inserisci:

- sesso
- eta
- altezza
- peso
- fattore attivita
- metodo BF
- tipo dieta
- peso ideale opzionale
- target BF opzionale
- macro preset
- proteine g/kg
- grassi g/kg

## Login Google

Per il pulsante Google crea un client OAuth Web su Google Cloud e aggiungi tra gli `Authorized JavaScript origins` gli URL dove userai l'app, ad esempio:

- `http://127.0.0.1:8010`
- `http://localhost:8010`

Lato server serve solo `GOOGLE_CLIENT_ID` per verificare il token ricevuto dal client.

## Icona personalizzata

Puoi usare una tua icona senza cambiare codice:

1. metti il file dentro `static/`
2. chiamalo ad esempio `pwa-icon.png`
3. riavvia l'app

Oppure imposta:

```powershell
$env:PWA_ICON_FILE="mia-icona.png"
```

## Note

- il layout e pensato per mobile
- il profilo salva storico piani e check-in
- il bottone `Scarica CSV` esporta lo storico dei piani
