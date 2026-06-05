import Testing
@testable import HubViewApp
import Foundation

@Test
func commandLineConfigReadsExplicitFlags() {
    let config = HubCLIConfig(
        repoRoot: "/repo",
        pythonBin: "/python",
        databaseURL: "postgres://db",
        obsidianExportDir: "/obsidian"
    )

    #expect(config.repoRoot == "/repo")
    #expect(config.pythonBin == "/python")
    #expect(config.databaseURL == "postgres://db")
    #expect(config.obsidianExportDir == "/obsidian")
}

@Test
func bundledRuntimeConfigDecodesExpectedFields() {
    let data = Data(
        """
        {
          "repoRoot": "/repo",
          "pythonBin": "/python",
          "databaseURL": "postgres://db",
          "obsidianExportDir": "/vault"
        }
        """.utf8
    )

    let config = HubCLIConfig.decodeBundledRuntimeConfig(from: data)

    #expect(config?.repoRoot == "/repo")
    #expect(config?.pythonBin == "/python")
    #expect(config?.databaseURL == "postgres://db")
    #expect(config?.obsidianExportDir == "/vault")
}

@MainActor
@Test
func hubStoreShowHomeClearsProjectSelection() {
    let store = HubStore(
        cli: HubCLI(
            config: HubCLIConfig(
                repoRoot: "/repo",
                pythonBin: "/python",
                databaseURL: "postgres://db",
                obsidianExportDir: "/vault"
            )
        )
    )

    store.selectedProjectID = "central-agent-data-hub"
    store.detail = HubViewModel(
        project: ProjectRecord(
            name: "Central Agent Data Hub",
            slug: "central-agent-data-hub",
            description: nil,
            status: "active",
            metadata: nil,
            updatedAt: nil
        ),
        counts: Counts(
            documents: 0,
            facts: 0,
            decisions: 0,
            openQuestions: 0,
            risks: 0,
            reports: 0
        ),
        facts: [],
        decisions: [],
        risks: [],
        openQuestions: [],
        reports: [],
        relations: [],
        quality: QualityPayload(
            score: 100,
            status: "healthy",
            relationCount: 0,
            relationCoverage: 0,
            factsWithoutSource: [],
            decisionsWithoutRationale: [],
            risksWithoutMitigation: [],
            openQuestions: []
        )
    )
    store.errorMessage = "Detail konnte nicht geladen werden."

    store.showHome()

    #expect(store.selectedProjectID == nil)
    #expect(store.detail == nil)
    #expect(store.errorMessage == nil)
}
