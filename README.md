# Skridsko isobservasjoner for Home Assistant

Integrasjonen ser jevnlig etter nye isobservasjoner i interesseområdet ditt på tur.skridsko.net. Nye observasjoner sendes videre som e-post med bilder og kart inne i meldingen, og/eller som push til mobilen. Alt settes opp i brukergrensesnittet.

## Hva du får

- **Oppsett i UI:** innloggingsnøkkel, e-post og/eller push, antall bilder, kart og hvor ofte Skridsko sjekkes.
- **Reparer-varsel** når innloggingen går ut. Du limer inn ny nøkkel der, og alt som har kommet i mellomtiden blir sendt etterpå.
- **Entiteter:** Innlogget, Siste observasjon (med alle detaljer og koordinater som attributter), Status, Neste sjekk, Varsler sendt i dag, Siste bilde, knappene «Se etter nye observasjoner nå» og «Send siste observasjon på nytt», og bryteren «Varsler aktivert».
- **Dashbordkort:** `custom:skridsko-card` registreres automatisk.
- **Kart:** kartbilde fra Kartverket med markør i e-posten, lenker til Norgeskart og Google Maps. Observasjonen kan også vises på kartkort i Home Assistant.
- **Loggbok:** hvert varsel, og når innloggingen går ut eller virker igjen.
- **Hendelse** `skridsko_observation` som du kan bruke i egne automatiseringer.

## Installering

1. Kopier mappa `custom_components/skridsko` til `/config/custom_components/skridsko` i Home Assistant (med Samba- eller File Editor-tillegget).
   Alternativt i HACS: ⋮ → *Egendefinerte repositorier* → legg inn repoet som *Integrasjon*.
2. Start Home Assistant på nytt.

## Oppsett

**PHPSESSID:** logg inn på tur.skridsko.net i Chrome → F12 → *Application* → *Cookies* → `https://tur.skridsko.net` → kopier *Value* for `PHPSESSID`.

**App-passord** (bare hvis du vil ha e-post): myaccount.google.com, logget inn på kontoen som skal sende → Sikkerhet → Totrinnsbekreftelse → App-passord.

Innstillinger → Enheter og tjenester → Legg til integrasjon → **Skridsko isobservasjoner**:

1. Lim inn PHPSESSID. Innloggingen sjekkes med en gang.
2. **Levering:**
   - *Send e-post* → *Innebygd Gmail-sending*: konto som sender, app-passordet og til-adressen. Du kan også velge en eksisterende varslingstjeneste.
   - *Push-varsel til mobil*: velg telefonen(e). Push har med det første bildet og knapper for observasjonen og kartet.
   - *Bare push når isen er meldt åkbar*: du får alt på e-post, men bare de gode nyhetene på telefonen.
   - *Maks bilder*, *Ta med kart* og *korteste/lengste intervall* for sjekkene.

Alt kan endres senere via **Konfigurer**.

Første gang lista leses, regnes alt som ligger der som sett. Du får altså bare varsel om observasjoner som kommer etterpå.

## Slik virker sjekkene

Hver sjekk er én visning av observasjonslista. Den finner nye observasjoner og holder samtidig innloggingen i live (Skridsko logger deg ut etter en tid uten aktivitet). Etter hver sjekk trekkes en ny tilfeldig ventetid mellom korteste og lengste intervall (standard 9–21 min), pluss opptil 40 sekunder. Nye observasjoner kommer altså i snitt etter ca. 7 minutter og senest etter ca. 21.

Går innloggingen ut, får du et Reparer-varsel i Home Assistant og en melding på e-post/push.

## Valgfritt: raskere med Skridskos e-postvarsler

Vil du ha observasjonene i løpet av sekunder i stedet for minutter, kan integrasjonen i tillegg lytte på Skridskos e-postvarsler. Lista sjekkes fortsatt, og samme observasjon sendes aldri to ganger.

1. **Gmail-filter** på kontoen som får varslene: *Filtre og blokkerte adresser* → *Opprett nytt filter* → **Fra:** `webadmin@skridsko.net` → *Videresend til* kontoen Home Assistant leser (videresendingsadressen må bekreftes først under *Videresending og POP/IMAP*).
2. **IMAP-integrasjonen**: server `imap.gmail.com`, port `993`, app-passord. Under *Konfigurer* setter du **Søk** til `UNSEEN OR FROM skridsko.net (FROM din.adresse@gmail.com BODY isobservationer)`, og lar meldingsteksten være med i hendelsene.
3. Skridsko → **Konfigurer** → slå på *Reager også straks på Skridskos e-postvarsler* og velg e-postkontoen.

Integrasjonen godtar bare e-post fra skridsko.net, eller Skridsko-varsler du har videresendt for hånd.

## Dashbordkort

Rediger dashbord → *Legg til kort* → søk «Skridsko». Eller i kodevisning:

```yaml
type: custom:skridsko-card
history: 3
```

Kortet finner entitetene selv.

## Kjente begrensninger

- Bildene og kartbildene lagres i `/config/www/skridsko/` (de siste 80 beholdes).
- Kartbildet krever Pillow, som normalt følger med Home Assistant. Uten Pillow sendes bare kartlenkene.
- Kartbildet bruker Kartverkets topokart, som bare dekker Norge. For vann i Sverige brukes OpenStreetMap bare hvis Kartverket ikke svarer.
- Hvor lenge en innlogging varer hos Skridsko, er ukjent. Senk lengste intervall hvis du ofte må logge inn på nytt.
