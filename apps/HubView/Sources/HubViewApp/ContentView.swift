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
                Text("Read-only")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            ToolbarItem(placement: .automatic) {
                Button {
                    Task { await store.reload() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .help("Reload")
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
                VStack(alignment: .leading, spacing: 4) {
                    Text("Hub View")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(.primary)
                    Text("Read-only review surface for Agent Data Hub")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textCase(nil)
                }
                .padding(.bottom, 8)
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("Projects")
        .frame(minWidth: 280, idealWidth: 300)
        .overlay {
            if store.projects.isEmpty && !store.isLoadingProjects && store.errorMessage == nil {
                ContentUnavailableView("No active projects", systemImage: "tray")
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
                ContentUnavailableView("Select a project", systemImage: "sidebar.left")
            }
        }
    }
}

private struct ProjectRow: View {
    let project: ProjectSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(project.name)
                .font(.body.weight(.medium))
                .foregroundStyle(.primary)
                .lineLimit(1)
            Text(project.slug)
                .font(.caption)
                .foregroundStyle(.secondary)
            if let description = project.description, !description.isEmpty {
                Text(description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 6)
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
                    title: "Open questions",
                    rows: detail.openQuestions,
                    emptyText: "No unresolved questions are visible."
                ) { row in
                    ItemRow(title: row.question, subtitle: row.answer)
                }
                section(
                    title: "Risks",
                    rows: detail.risks,
                    emptyText: "No active risks are visible."
                ) { row in
                    ItemRow(title: row.title, subtitle: row.impact ?? row.mitigation)
                }
                section(
                    title: "Decisions",
                    rows: detail.decisions,
                    emptyText: "No active decisions are visible."
                ) { row in
                    ItemRow(title: row.decision, subtitle: row.rationale)
                }
                section(
                    title: "Facts",
                    rows: detail.facts,
                    emptyText: "No reviewed facts are visible."
                ) { row in
                    ItemRow(title: row.statement, subtitle: row.source)
                }
                section(
                    title: "Reports",
                    rows: detail.reports,
                    emptyText: "No reports are visible."
                ) { row in
                    ItemRow(title: row.title, subtitle: row.summary)
                }
                section(
                    title: "Relations",
                    rows: detail.relations,
                    emptyText: "No relations are visible."
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
        VStack(alignment: .leading, spacing: 10) {
            Text(detail.project.name)
                .font(.system(size: 30, weight: .semibold))
                .foregroundStyle(.primary)
            headerMeta
            if let description = detail.project.description, !description.isEmpty {
                Text(description)
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text("Verified context for humans and agents.")
                .font(.caption)
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
                    label: "Memory",
                    value: "\(detail.counts.total)",
                    note: "\(detail.counts.facts) facts, \(detail.counts.reports) reports"
                )
                Divider()
                MetricCell(
                    label: "Open work",
                    value: "\(detail.counts.openQuestions + detail.counts.risks)",
                    note: "\(detail.counts.openQuestions) questions, \(detail.counts.risks) risks"
                )
                Divider()
                MetricCell(
                    label: "Quality",
                    value: "\(detail.quality.score)",
                    note: detail.quality.status
                )
            }
            Divider()
            SummaryRow(label: "Status", value: detail.project.status)
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
                .font(.caption)
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
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 24, weight: .semibold))
                .foregroundStyle(.primary)
            Text(note)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 18)
        .padding(.vertical, 16)
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
                    .font(.caption)
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
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.body)
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
            if let subtitle, !subtitle.isEmpty {
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 12)
    }
}

private struct RelationItemView: View {
    let row: RelationRow

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(row.sourceSummary ?? "Source")
                .font(.body)
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 8) {
                Rectangle()
                    .fill(Color.secondary.opacity(0.35))
                    .frame(width: 18, height: 1)
                Text(relationLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(row.targetSummary ?? "Target")
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 12)
    }

    private var relationLabel: String {
        row.relationType.replacingOccurrences(of: "_", with: " ")
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
            Label("Hub View could not load data", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        }
    }
}
