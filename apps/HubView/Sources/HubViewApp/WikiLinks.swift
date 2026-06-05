import AppKit
import Foundation

enum MemoryExportFolder: String {
    case reports = "Reports"
    case decisions = "Decisions"
    case facts = "Facts"
    case openQuestions = "Open Questions"
    case risks = "Risks"
}

struct WikiLinkResolver {
    let exportDir: String?

    func reportPath(_ row: ReportRow) -> URL? {
        path(folder: .reports, title: row.title, id: row.id)
    }

    func decisionPath(_ row: DecisionRow) -> URL? {
        path(folder: .decisions, title: row.decision, id: row.id)
    }

    func factPath(_ row: FactRow) -> URL? {
        path(folder: .facts, title: row.statement, id: row.id)
    }

    func openQuestionPath(_ row: OpenQuestionRow) -> URL? {
        path(folder: .openQuestions, title: row.question, id: row.id)
    }

    func riskPath(_ row: RiskRow) -> URL? {
        path(folder: .risks, title: row.title, id: row.id)
    }

    func openIfPresent(_ url: URL?) {
        guard let url, FileManager.default.fileExists(atPath: url.path) else {
            return
        }
        NSWorkspace.shared.open(url)
    }

    func existingPath(_ url: URL?) -> URL? {
        guard let url, FileManager.default.fileExists(atPath: url.path) else {
            return nil
        }
        return url
    }

    private func path(folder: MemoryExportFolder, title: String, id: String) -> URL? {
        guard let exportDir, !exportDir.isEmpty else {
            return nil
        }
        let root = URL(fileURLWithPath: exportDir, isDirectory: true)
        return root
            .appendingPathComponent(folder.rawValue, isDirectory: true)
            .appendingPathComponent(filename(title: title, id: id), isDirectory: false)
    }

    private func filename(title: String, id: String) -> String {
        let stem = slugify(title)
        let suffix = idSuffix(id)
        return suffix.isEmpty ? "\(stem).md" : "\(stem)-\(suffix).md"
    }

    private func idSuffix(_ value: String) -> String {
        let compact = value.replacingOccurrences(
            of: "[^A-Za-z0-9]",
            with: "",
            options: .regularExpression
        )
        return String(compact.suffix(8))
    }

    private func slugify(_ value: String) -> String {
        let lowercased = value.lowercased()
        let collapsed = lowercased.replacingOccurrences(
            of: "[^a-z0-9]+",
            with: "-",
            options: .regularExpression
        )
        let trimmed = collapsed.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        let shortened = String(trimmed.prefix(80)).trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        return shortened.isEmpty ? "untitled" : shortened
    }
}
