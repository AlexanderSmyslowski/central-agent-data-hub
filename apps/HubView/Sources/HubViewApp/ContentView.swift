import SwiftUI

struct ContentView: View {
    @StateObject private var store: HubStore

    init(store: HubStore) {
        _store = StateObject(wrappedValue: store)
    }

    var body: some View {
        NavigationSplitView {
            SidebarView(store: store)
        } detail: {
            DetailContainerView(store: store)
        }
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
        List(selection: $store.selectedProjectID) {
            Section {
                ForEach(store.projects) { project in
                    ProjectRow(project: project)
                        .tag(project.id)
                }
            } header: {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Hub View")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(.primary)
                    Text("Leseflaeche fuer Agent Data Hub")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .textCase(nil)
                }
                .padding(.bottom, 10)
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("Projekte")
        .frame(minWidth: 280, idealWidth: 300)
        .overlay {
            if store.projects.isEmpty && !store.isLoadingProjects && store.errorMessage == nil {
                ContentUnavailableView("Keine aktiven Projekte", systemImage: "tray")
            }
        }
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
                ContentUnavailableView("Projekt auswaehlen", systemImage: "sidebar.left")
            }
        }
    }
}

private struct ProjectRow: View {
    let project: ProjectSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(project.name)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.primary)
                .lineLimit(1)
            Text(project.slug)
                .font(.caption2)
                .foregroundStyle(.secondary)
            if let description = project.description, !description.isEmpty {
                Text(description)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(.vertical, 4)
    }
}

private struct ProjectDetailView: View {
    let detail: HubViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                header
                summaryPanel
                section(
                    title: "Offene Fragen",
                    rows: detail.openQuestions,
                    emptyText: "Keine offenen Fragen sichtbar."
                ) { row in
                    ItemRow(title: row.question, subtitle: row.answer)
                }
                section(
                    title: "Risiken",
                    rows: detail.risks,
                    emptyText: "Keine aktiven Risiken sichtbar."
                ) { row in
                    ItemRow(title: row.title, subtitle: row.impact ?? row.mitigation)
                }
                section(
                    title: "Entscheidungen",
                    rows: detail.decisions,
                    emptyText: "Keine aktiven Entscheidungen sichtbar."
                ) { row in
                    ItemRow(title: row.decision, subtitle: row.rationale)
                }
                section(
                    title: "Fakten",
                    rows: detail.facts,
                    emptyText: "Keine geprueften Fakten sichtbar."
                ) { row in
                    ItemRow(title: row.statement, subtitle: row.source)
                }
                section(
                    title: "Berichte",
                    rows: detail.reports,
                    emptyText: "Keine Berichte sichtbar."
                ) { row in
                    ItemRow(title: row.title, subtitle: row.summary)
                }
                section(
                    title: "Verknuepfungen",
                    rows: detail.relations,
                    emptyText: "Keine Verknuepfungen sichtbar."
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
            Text("Gepruefter Kontext fuer Menschen und Agenten.")
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

    private var summaryPanel: some View {
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                MetricCell(
                    label: "Wissen",
                    value: "\(detail.counts.total)",
                    note: "\(detail.counts.facts) Fakten, \(detail.counts.reports) Reports"
                )
                Divider()
                MetricCell(
                    label: "Offen",
                    value: "\(detail.counts.openQuestions + detail.counts.risks)",
                    note: "\(detail.counts.openQuestions) Fragen, \(detail.counts.risks) Risiken"
                )
                Divider()
                MetricCell(
                    label: "Qualitaet",
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

    @ViewBuilder
    private func section<Row, Content: View>(
        title: String,
        rows: [Row],
        emptyText: String,
        @ViewBuilder content: @escaping (Row) -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionHeader(title: title, count: rows.count)
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
}

private struct SectionHeader: View {
    let title: String
    let count: Int

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(title)
                .font(.headline)
                .foregroundStyle(.primary)
            Text("\(count)")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
            Spacer(minLength: 0)
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
            return "stuetzt"
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
