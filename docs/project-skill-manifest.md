# Project Skill Manifest

Das Project Skill Manifest ist eine optionale Datei im jeweiligen Repo. Es sagt
Codex/Hermes vor Arbeitsbeginn, welche Dokumente, Skills, Qualitätsprüfungen
und Grenzen für dieses Projekt gelten.

Es ist bewusst kein neuer Hub-Speicher. Der Hub speichert das geprüfte
Gedächtnis. `AGENTS.md` bleibt der Arbeitsvertrag im Repo. Skills bleiben
Ausführungshilfe. Obsidian und Hub View bleiben Lese- und Review-Flächen.

## Warum es das gibt

Agenten arbeiten verlässlicher, wenn sie die richtigen Arbeitsregeln kennen.
Das Manifest ist die Karte zu diesen Regeln, ohne lange technische Texte in
PostgreSQL zu kopieren.

Nutze es, wenn ein Projekt mehrere wichtige Anweisungsdateien hat oder wenn
bestimmte Skills leicht übersehen werden.

## Empfohlener Ort

```text
.agent-data-hub/project-skill-manifest.yml
```

Der Pfad ist absichtlich repo-lokal. Ein Hub-Projekt kann später darauf
verweisen, aber die Datei selbst bleibt nah am Code und an den Dokumenten, die
sie beschreibt.

## Was hier hineingehört

- kurze Listen wichtiger Repo-Dokumente
- empfohlene oder verpflichtende Skills
- Qualitätsprüfungen vor Finish oder Handoff
- klare Grenzen und Nicht-Ziele
- eine kurze Aussage, was ins Hub-Gedächtnis gehört und was nicht

## Was hier nicht hineingehört

- lange technische Regeltexte aus Framework-Dokumentation
- Roh-Chatverläufe, private Notizen, Zugangsdaten oder Kundendaten
- Secrets, API keys, Tokens, FTP-Zugänge, Rohrechnungen oder Deployment-Details
- Projektfakten, die als geprüftes Hub-Gedächtnis gespeichert werden sollten
- automatisch erzeugte Tool- oder Dependency-Ausgaben

## Example

See:

```text
/Users/alexandersmyslowski/Projects/central-agent-data-hub/docs/examples/project-skill-manifest.yml
```

## Beziehung zum Hub

Die drei Teile bleiben getrennt:

- **Gedächtnis**: Was wissen wir dauerhaft geprüft?
- **Arbeitskontext**: Was gilt für diesen Lauf?
- **Arbeitsregeln**: Wie soll in diesem Repo gearbeitet werden?

Das Manifest gehört zu den Arbeitsregeln. Es speichert nicht das
Projektgedächtnis. Es zeigt nur, welche Regelquellen ein Agent zuerst beachten
soll.

Wenn aus einem Manifest-Eintrag ein dauerhafter Projektfakt oder eine
Entscheidung wird, schreibe diese kurze geprüfte Aussage über
`scripts/project_remember.sh` in den Hub. Kopiere nicht das ganze Manifest in
das Hub-Gedächtnis.

## Architekturregel

Vor dem Ausbau fragen:

- Reduziert es echte Verwirrung im Agentenalltag?
- Entfernt es einen manuellen Schritt?
- Bleibt der Hub kleiner als die Arbeit, die er koordiniert?
- Ist die Grenze für einen strengen Code-Review sauber?

Wenn die Antwort nein ist, bleibt es Dokumentation.
