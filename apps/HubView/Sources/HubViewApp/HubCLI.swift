import Foundation

struct HubCLIConfig {
    let repoRoot: String
    let pythonBin: String
    let databaseURL: String
    let obsidianExportDir: String?

    static func fromCommandLine() -> HubCLIConfig {
        let arguments = Array(CommandLine.arguments.dropFirst())
        func value(for flag: String) -> String? {
            guard let index = arguments.firstIndex(of: flag), arguments.indices.contains(index + 1) else {
                return nil
            }
            return arguments[index + 1]
        }

        if let explicitRepoRoot = value(for: "--repo-root"),
           let explicitPythonBin = value(for: "--python-bin"),
           let explicitDatabaseURL = value(for: "--database-url")
        {
            return HubCLIConfig(
                repoRoot: explicitRepoRoot,
                pythonBin: explicitPythonBin,
                databaseURL: explicitDatabaseURL,
                obsidianExportDir: value(for: "--obsidian-export-dir")
            )
        }

        if let bundled = bundledRuntimeConfig() {
            return bundled
        }

        return HubCLIConfig(
            repoRoot: value(for: "--repo-root") ?? FileManager.default.currentDirectoryPath,
            pythonBin: value(for: "--python-bin") ?? "/usr/bin/python3",
            databaseURL: value(for: "--database-url") ?? "",
            obsidianExportDir: value(for: "--obsidian-export-dir")
        )
    }

    private static func bundledRuntimeConfig() -> HubCLIConfig? {
        guard let url = Bundle.main.url(forResource: "runtime-config", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let config = decodeBundledRuntimeConfig(from: data)
        else {
            return nil
        }

        return config
    }

    static func decodeBundledRuntimeConfig(from data: Data) -> HubCLIConfig? {
        guard let payload = try? JSONDecoder().decode(BundledRuntimeConfig.self, from: data) else {
            return nil
        }

        return HubCLIConfig(
            repoRoot: payload.repoRoot,
            pythonBin: payload.pythonBin,
            databaseURL: payload.databaseURL,
            obsidianExportDir: payload.obsidianExportDir
        )
    }
}

private struct BundledRuntimeConfig: Decodable {
    let repoRoot: String
    let pythonBin: String
    let databaseURL: String
    let obsidianExportDir: String?
}

enum HubCLIError: LocalizedError {
    case missingDatabaseURL
    case commandFailed(String)
    case emptyOutput

    var errorDescription: String? {
        switch self {
        case .missingDatabaseURL:
            return "DATABASE_URL fehlt. Bitte Hub View ueber das Projekt-Startscript oeffnen."
        case .commandFailed(let message):
            return message
        case .emptyOutput:
            return "Der Agent Data Hub hat keine Ausgabe zurueckgegeben."
        }
    }
}

struct HubCLI {
    let config: HubCLIConfig
    let decoder: JSONDecoder = JSONDecoder()

    func fetchProjects() throws -> [ProjectSummary] {
        try decode(["projects", "--format", "json"], as: [ProjectSummary].self)
    }

    func fetchProjectView(slug: String) throws -> HubViewModel {
        let compiled = try decode(
            ["compile", "--project", slug, "--format", "json"],
            as: CompiledPayload.self
        )
        let quality = try decode(
            ["quality", "--project", slug, "--format", "json"],
            as: QualityPayload.self
        )
        return HubViewModel(
            project: compiled.project,
            counts: compiled.counts,
            facts: compiled.facts,
            decisions: compiled.decisions,
            risks: compiled.risks,
            openQuestions: compiled.openQuestions,
            reports: compiled.reports,
            relations: compiled.relations,
            quality: quality
        )
    }

    private func decode<T: Decodable>(_ arguments: [String], as type: T.Type) throws -> T {
        let data = try run(arguments)
        return try decoder.decode(T.self, from: data)
    }

    private func run(_ arguments: [String]) throws -> Data {
        guard !config.databaseURL.isEmpty else {
            throw HubCLIError.missingDatabaseURL
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: config.pythonBin)
        process.arguments = ["-m", "agent_hub.cli"] + arguments
        process.currentDirectoryURL = URL(fileURLWithPath: config.repoRoot)

        var environment = ProcessInfo.processInfo.environment
        environment["DATABASE_URL"] = config.databaseURL
        if let exportDir = config.obsidianExportDir, !exportDir.isEmpty {
            environment["OBSIDIAN_EXPORT_DIR"] = exportDir
        }
        process.environment = environment

        let output = Pipe()
        let error = Pipe()
        process.standardOutput = output
        process.standardError = error

        try process.run()
        process.waitUntilExit()

        let outputData = output.fileHandleForReading.readDataToEndOfFile()
        let errorData = error.fileHandleForReading.readDataToEndOfFile()

        guard process.terminationStatus == 0 else {
            let message = String(data: errorData, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            throw HubCLIError.commandFailed(message?.isEmpty == false ? message! : "Der Agent Data Hub Befehl ist fehlgeschlagen.")
        }
        guard !outputData.isEmpty else {
            throw HubCLIError.emptyOutput
        }
        return outputData
    }
}
