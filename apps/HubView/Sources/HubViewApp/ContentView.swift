import SwiftUI

struct ContentView: View {
    @StateObject private var store: HubStore

    init(store: HubStore) {
        _store = StateObject(wrappedValue: store)
    }

    var body: some View {
        HStack(spacing: 0) {
            SidebarView(store: store)
            Divider()
            DetailContainerView(store: store)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Text("Nur lesen")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            ToolbarItem(placement: .automatic) {
                Button {
                    Task { await store.reload() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .help("Neu laden")
            }
        }
        .task {
            await store.load()
            await store.loadSelectedProject()
        }
        .task(id: store.selectedProjectID) {
            await store.loadSelectedProject()
        }
    }
}

private struct SidebarView: View {
    @ObservedObject var store: HubStore

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Hub View")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(.primary)
                Text("Lesefläche für Agent Data Hub")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 20)
            .padding(.top, 24)
            .padding(.bottom, 14)

            if store.projects.isEmpty && !store.isLoadingProjects && store.errorMessage == nil {
                ContentUnavailableView("Keine aktiven Projekte", systemImage: "tray")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 3) {
                        ForEach(store.projects) { project in
                            Button {
                                store.selectedProjectID = project.id
                            } label: {
                                ProjectRow(
                                    project: project,
                                    isSelected: project.id == store.selectedProjectID
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.bottom, 12)
                }
            }
        }
        .frame(width: 300)
        .background(.bar)
    }
}

private struct DetailContainerView: View {
    @ObservedObject var store: HubStore

    var body: some View {
        Group {
            if let detail = store.detail {
                ProjectDetailView(detail: detail)
            } else if store.isLoadingDetail || store.isLoadingProjects {
                ProgressView()
                    .controlSize(.large)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let message = store.errorMessage {
                ErrorView(message: message)
            } else {
                WelcomeView()
            }
        }
    }
}

private struct WelcomeView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 28) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Hub View")
                    .font(.system(size: 30, weight: .semibold))
                    .foregroundStyle(.primary)
                Text("Lesefläche für Agent Data Hub")
                    .font(.body)
                    .foregroundStyle(.secondary)
                Text("Wähle links ein Projekt. Hub View zeigt nur, was der Hub weiß. Es schreibt nichts zurück.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack(alignment: .top, spacing: 0) {
                ConceptCell(
                    title: "Gedächtnis",
                    text: "Was wir dauerhaft geprüft wissen.",
                    footnote: "liegt im Hub"
                )
                Divider()
                ConceptCell(
                    title: "Arbeitskontext",
                    text: "Was für den aktuellen Lauf gilt.",
                    footnote: "wird beim Start erzeugt"
                )
                Divider()
                ConceptCell(
                    title: "Arbeitsregeln",
                    text: "Wie gearbeitet werden soll.",
                    footnote: "liegt in Repo-Doku und Skills"
                )
            }
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color(nsColor: .controlBackgroundColor))
            )
        }
        .frame(maxWidth: 720, alignment: .leading)
        .padding(.horizontal, 44)
        .padding(.vertical, 42)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Color(nsColor: .windowBackgroundColor))
    }
}

private struct ProjectRow: View {
    let project: ProjectSummary
    let isSelected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(project.name)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(isSelected ? .white : .primary)
                .lineLimit(1)
            Text(project.slug)
                .font(.caption2)
                .foregroundStyle(isSelected ? .white.opacity(0.82) : .secondary)
            if let description = project.description, !description.isEmpty {
                Text(description)
                    .font(.caption2)
                    .foregroundStyle(isSelected ? .white.opacity(0.82) : .secondary)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(isSelected ? Color.accentColor : Color.clear)
        )
    }
}

private struct ProjectDetailView: View {
    let detail: HubViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                header
                introPanel
                systemMapPanel
                summaryPanel
                workingContextPanel
                MemoryDetailHeader()
                section(
                    title: "Offene Fragen",
                    description: "Punkte, die für dieses Projekt noch geklärt werden müssen.",
                    rows: detail.openQuestions,
                    emptyText: "Keine offenen Fragen sichtbar."
                ) { row in
                    ItemRow(title: row.question, subtitle: row.answer)
                }
                section(
                    title: "Risiken",
                    description: "Probleme oder Unsicherheiten, die Aufmerksamkeit brauchen.",
                    rows: detail.risks,
                    emptyText: "Keine aktiven Risiken sichtbar."
                ) { row in
                    ItemRow(title: row.title, subtitle: row.impact ?? row.mitigation)
                }
                section(
                    title: "Entscheidungen",
                    description: "Bewusst getroffene Festlegungen für dieses Projekt.",
                    rows: detail.decisions,
                    emptyText: "Keine aktiven Entscheidungen sichtbar."
                ) { row in
                    ItemRow(title: row.decision, subtitle: row.rationale)
                }
                section(
                    title: "Fakten",
                    description: "Geprüfte Informationen, auf die sich Menschen und Agenten stützen können.",
                    rows: detail.facts,
                    emptyText: "Keine geprüften Fakten sichtbar."
                ) { row in
                    ItemRow(title: row.statement, subtitle: row.source)
                }
                section(
                    title: "Berichte",
                    description: "Kurze Zusammenfassungen, Übergaben oder Tagesstände.",
                    rows: detail.reports,
                    emptyText: "Keine Berichte sichtbar."
                ) { row in
                    ItemRow(title: row.title, subtitle: row.summary)
                }
                section(
                    title: "Verknüpfungen",
                    description: "Beziehungen zwischen Fakten, Entscheidungen, Risiken und Berichten.",
                    rows: detail.relations,
                    emptyText: "Keine Verknüpfungen sichtbar."
                ) { row in
                    RelationItemView(row: row)
                }
            }
            .frame(maxWidth: 880, alignment: .leading)
            .padding(.horizontal, 44)
            .padding(.vertical, 36)
            .frame(maxWidth: .infinity, alignment: .center)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .textSelection(.enabled)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(detail.project.name)
                .font(.system(size: 28, weight: .semibold))
                .foregroundStyle(.primary)
            headerMeta
            if let description = detail.project.description, !description.isEmpty {
                Text(description)
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text("Geprüfter Kontext für Menschen und Agenten.")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    private var headerMeta: some View {
        HStack(spacing: 8) {
            Text(detail.project.slug)
            if let updated = formattedUpdatedAt(detail.project.updatedAt) {
                Text("•")
                Text(updated)
            }
        }
        .font(.subheadline)
        .foregroundStyle(.secondary)
    }

    private var introPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Was du hier siehst")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.primary)
            Text("Links wählst du ein Projekt. Rechts siehst du, was der Hub dazu weiß, was für Agentenläufe gilt und wo die Arbeitsregeln liegen.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 16)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
    }

    private var systemMapPanel: some View {
        HStack(alignment: .top, spacing: 0) {
            ConceptCell(
                title: "Gedächtnis",
                text: "Was wir dauerhaft geprüft wissen.",
                footnote: "liegt im Hub"
            )
            Divider()
            ConceptCell(
                title: "Arbeitskontext",
                text: "Was für den aktuellen Lauf gilt.",
                footnote: "wird beim Start erzeugt"
            )
            Divider()
            ConceptCell(
                title: "Arbeitsregeln",
                text: "Wie gearbeitet werden soll.",
                footnote: "liegt in Repo-Doku und Skills"
            )
        }
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
    }

    private var summaryPanel: some View {
        VStack(spacing: 0) {
            PanelIntro(
                title: "Gedächtnis",
                description: "Geprüftes Projektwissen aus PostgreSQL. Hub View zeigt es nur an."
            )
            Divider()
            HStack(spacing: 0) {
                MetricCell(
                    label: "Wissen",
                    value: "\(detail.counts.total)",
                    note: "\(detail.counts.facts) Fakten, \(detail.counts.reports) Berichte"
                )
                Divider()
                MetricCell(
                    label: "Offen",
                    value: "\(detail.counts.openQuestions + detail.counts.risks)",
                    note: "\(detail.counts.openQuestions) Fragen, \(detail.counts.risks) Risiken"
                )
                Divider()
                MetricCell(
                    label: "Qualität",
                    value: "\(detail.quality.score)",
                    note: qualityLabel(detail.quality.status)
                )
            }
            Divider()
            SummaryRow(label: "Status", value: statusLabel(detail.project.status))
        }
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
    }

    private var workingContextPanel: some View {
        VStack(spacing: 0) {
            PanelIntro(
                title: "Arbeitskontext",
                description: "Wird bei agent_start, compile oder context für einen konkreten Lauf zusammengestellt."
            )
            Divider()
            SummaryRow(
                label: "Arbeitsweise",
                value: workModeLabel(detail.project.metadata?.workMode)
            )
            SummaryRow(
                label: "Arbeitsregeln",
                value: rulesLocationText,
                showsDivider: false
            )
        }
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
    }

    private var rulesLocationText: String {
        if let manifest = detail.project.metadata?.skillManifest, !manifest.isEmpty {
            return "Im Projekt-Repo: AGENTS.md, Repo-Doku, Skills und \(manifest)."
        }
        if detail.project.metadata?.localPath?.isEmpty == false {
            return "Im Projekt-Repo: AGENTS.md, Repo-Doku, Skills und optional .agent-data-hub/project-skill-manifest.yml."
        }
        return "In Skills, AGENTS.md und Repo-Dokumenten. Sie werden nicht als Hub-Gedächtnis gespeichert."
    }

    @ViewBuilder
    private func section<Row, Content: View>(
        title: String,
        description: String,
        rows: [Row],
        emptyText: String,
        @ViewBuilder content: @escaping (Row) -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionHeader(title: title, description: description, count: rows.count)
            if rows.isEmpty {
                QuietEmpty(text: emptyText)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(rows.enumerated()), id: \.offset) { index, row in
                        content(row)
                        if index < rows.count - 1 {
                            Divider()
                        }
                    }
                }
            }
        }
    }

    private func formattedUpdatedAt(_ value: String?) -> String? {
        guard let value, !value.isEmpty else { return nil }
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let fallbackParser = ISO8601DateFormatter()

        let date = parser.date(from: value) ?? fallbackParser.date(from: value)
        guard let date else { return nil }

        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }

    private func statusLabel(_ raw: String) -> String {
        switch raw.lowercased() {
        case "active":
            return "aktiv"
        case "planned":
            return "geplant"
        case "archived":
            return "archiviert"
        default:
            return raw
        }
    }

    private func qualityLabel(_ raw: String) -> String {
        switch raw.lowercased() {
        case "healthy":
            return "gesund"
        case "warning":
            return "Hinweis"
        case "error":
            return "Fehler"
        default:
            return raw
        }
    }

    private func workModeLabel(_ raw: String?) -> String {
        guard let raw, !raw.isEmpty else {
            return "kein Arbeitsmodus hinterlegt"
        }
        return raw.replacingOccurrences(of: "-", with: " ")
    }
}

private struct PanelIntro: View {
    let title: String
    let description: String

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.primary)
            Text(description)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 18)
        .padding(.vertical, 15)
    }
}

private struct ConceptCell: View {
    let title: String
    let text: String
    let footnote: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.primary)
            Text(text)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Text(footnote)
                .font(.caption2)
                .foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 18)
        .padding(.vertical, 15)
    }
}

private struct MemoryDetailHeader: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text("Gedächtnis im Detail")
                .font(.headline)
                .foregroundStyle(.primary)
            Text("Diese Einträge sind die geprüfte Projekterinnerung. Sie sind keine Arbeitsregeln und kein Roh-Chatverlauf.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct SectionHeader: View {
    let title: String
    let description: String
    let count: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(.primary)
                Text("\(count)")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
                Spacer(minLength: 0)
            }
            Text(description)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct MetricCell: View {
    let label: String
    let value: String
    let note: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(.primary)
            Text(note)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 18)
        .padding(.vertical, 15)
    }
}

private struct SummaryRow: View {
    let label: String
    let value: String
    var showsDivider: Bool = true

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 16) {
                Text(label)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .frame(width: 96, alignment: .leading)
                Text(value)
                    .font(.body)
                    .foregroundStyle(.primary)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 14)
            if showsDivider {
                Divider()
                    .padding(.leading, 18)
            }
        }
    }
}

private struct ItemRow: View {
    let title: String
    let subtitle: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.body)
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
            if let subtitle, !subtitle.isEmpty {
                Text(subtitle)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 10)
    }
}

private struct RelationItemView: View {
    let row: RelationRow

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(row.sourceSummary ?? "Quelle")
                .font(.body)
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 8) {
                Rectangle()
                    .fill(Color.secondary.opacity(0.35))
                    .frame(width: 18, height: 1)
                Text(relationLabel)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Text(row.targetSummary ?? "Ziel")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 10)
    }

    private var relationLabel: String {
        switch row.relationType.lowercased() {
        case "supports":
            return "stützt"
        case "references":
            return "verweist auf"
        case "mitigates":
            return "mindert"
        case "answers":
            return "beantwortet"
        case "blocks":
            return "blockiert"
        default:
            return row.relationType.replacingOccurrences(of: "_", with: " ")
        }
    }
}

private struct QuietEmpty: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.callout)
            .foregroundStyle(.secondary)
    }
}

private struct ErrorView: View {
    let message: String

    var body: some View {
        ContentUnavailableView {
            Label("Hub View konnte die Daten nicht laden", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        }
    }
}
