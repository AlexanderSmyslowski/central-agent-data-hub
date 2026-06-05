import Foundation

struct WikiPreviewDocument: Equatable {
    let title: String
    let kind: String
    let url: URL
    let content: String
}

enum WikiPreviewLoader {
    static func load(title: String, kind: String, url: URL?) -> WikiPreviewDocument? {
        guard let url, FileManager.default.fileExists(atPath: url.path) else {
            return nil
        }
        guard let data = try? Data(contentsOf: url),
              let text = String(data: data, encoding: .utf8) else {
            return nil
        }

        let cleaned = stripFrontmatter(from: text)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let content = cleaned.isEmpty ? "Keine lesbaren Inhalte gefunden." : cleaned

        return WikiPreviewDocument(title: title, kind: kind, url: url, content: content)
    }

    static func stripFrontmatter(from markdown: String) -> String {
        guard markdown.hasPrefix("---\n") || markdown.hasPrefix("---\r\n") else {
            return markdown
        }

        let newline = markdown.hasPrefix("---\r\n") ? "\r\n" : "\n"
        let delimiter = "\(newline)---"

        guard let range = markdown.range(of: delimiter) else {
            return markdown
        }

        let afterDelimiter = markdown[range.upperBound...]
        if afterDelimiter.hasPrefix("\r\n") {
            return String(afterDelimiter.dropFirst(2))
        }
        if afterDelimiter.hasPrefix("\n") {
            return String(afterDelimiter.dropFirst())
        }
        return String(afterDelimiter)
    }
}
