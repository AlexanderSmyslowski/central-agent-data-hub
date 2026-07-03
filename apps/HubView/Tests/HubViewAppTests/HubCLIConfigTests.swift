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

@Test
func projectMetadataDecodesCodexWorkspaceRoot() throws {
    let data = Data(
        """
        {
          "project_type": "ops",
          "work_mode": "central-hub-start-finish",
          "local_path": "/repo",
          "codex_workspace_root": "/path/to/Agent Data Hub"
        }
        """.utf8
    )

    let metadata = try JSONDecoder().decode(ProjectMetadata.self, from: data)

    #expect(metadata.codexWorkspaceRoot == "/path/to/Agent Data Hub")
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
    store.detail = sampleHubViewModel()
    store.preview = WikiPreviewDocument(
        title: "Preview",
        kind: "Fakt",
        url: URL(fileURLWithPath: "/vault/Facts/preview.md"),
        content: "Hallo"
    )
    store.errorMessage = "Detail konnte nicht geladen werden."
    store.isLoadingDetail = true

    store.showHome()

    #expect(store.selectedProjectID == nil)
    #expect(store.detail == nil)
    #expect(store.preview == nil)
    #expect(store.errorMessage == nil)
    #expect(store.isLoadingDetail == false)
}

@MainActor
@Test
func hubStoreSelectProjectClearsStaleDetailImmediately() {
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

    store.selectedProjectID = nil
    store.detail = sampleHubViewModel()
    store.preview = WikiPreviewDocument(
        title: "Alt",
        kind: "Bericht",
        url: URL(fileURLWithPath: "/vault/Reports/old.md"),
        content: "Alt"
    )
    store.errorMessage = "Alte Meldung."

    store.selectProject("demo-website")

    #expect(store.selectedProjectID == "demo-website")
    #expect(store.detail == nil)
    #expect(store.preview == nil)
    #expect(store.errorMessage == nil)
    #expect(store.isLoadingDetail == true)
}

@Test
func wikiLinkResolverBuildsFactExportPathLikeHubExport() {
    let resolver = WikiLinkResolver(exportDir: "/vault")
    let row = FactRow(
        id: "20000000-0000-4000-8000-000000000204",
        statement: "The Central Agent Data Hub is the shared agentic work memory for Codex/Hermes.",
        source: nil,
        confidence: nil,
        status: "active"
    )

    let path = resolver.factPath(row)

    #expect(path?.path == "/vault/Facts/the-central-agent-data-hub-is-the-shared-agentic-work-memory-for-codex-hermes-00000204.md")
}

@Test
func wikiLinkResolverBuildsReportExportPathLikeHubExport() {
    let resolver = WikiLinkResolver(exportDir: "/vault")
    let row = ReportRow(
        id: "20000000-0000-4000-8000-000000000602",
        title: "Daily Report - Central Agent Data Hub - 2026-05-29",
        reportType: "daily",
        summary: nil,
        status: "published"
    )

    let path = resolver.reportPath(row)

    #expect(path?.path == "/vault/Reports/daily-report-central-agent-data-hub-2026-05-29-00000602.md")
}

@Test
func wikiPreviewLoaderStripsFrontmatter() {
    let markdown = """
    ---
    title: Test
    status: active
    ---
    # Ueberschrift

    Inhalt
    """

    let cleaned = WikiPreviewLoader.stripFrontmatter(from: markdown)

    #expect(cleaned == "# Ueberschrift\n\nInhalt")
}

private func sampleHubViewModel() -> HubViewModel {
    HubViewModel(
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
}
