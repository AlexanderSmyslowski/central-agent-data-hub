import Foundation

struct ProjectMetadata: Decodable, Hashable {
    let projectType: String?
    let workMode: String?
    let localPath: String?
    let skillManifest: String?

    private enum CodingKeys: String, CodingKey {
        case projectType = "project_type"
        case workMode = "work_mode"
        case localPath = "local_path"
        case skillManifest = "skill_manifest"
    }
}

struct ProjectSummary: Decodable, Identifiable, Hashable {
    let slug: String
    let name: String
    let status: String
    let description: String?
    let metadata: ProjectMetadata?

    var id: String { slug }
}

struct ProjectRecord: Decodable {
    let name: String
    let slug: String
    let description: String?
    let status: String
    let metadata: ProjectMetadata?
    let updatedAt: String?

    private enum CodingKeys: String, CodingKey {
        case name
        case slug
        case description
        case status
        case metadata
        case updatedAt = "updated_at"
    }
}

struct Counts: Decodable {
    let documents: Int
    let facts: Int
    let decisions: Int
    let openQuestions: Int
    let risks: Int
    let reports: Int

    private enum CodingKeys: String, CodingKey {
        case documents
        case facts
        case decisions
        case openQuestions = "open_questions"
        case risks
        case reports
    }

    var total: Int {
        facts + decisions + openQuestions + risks + reports
    }
}

struct FactRow: Decodable, Identifiable {
    let id: String
    let statement: String
    let source: String?
    let confidence: String?
    let status: String
}

struct DecisionRow: Decodable, Identifiable {
    let id: String
    let decision: String
    let rationale: String?
    let consequences: String?
    let status: String
}

struct RiskRow: Decodable, Identifiable {
    let id: String
    let title: String
    let severity: String?
    let impact: String?
    let mitigation: String?
    let status: String
}

struct OpenQuestionRow: Decodable, Identifiable {
    let id: String
    let question: String
    let answer: String?
    let status: String
}

struct ReportRow: Decodable, Identifiable {
    let id: String
    let title: String
    let reportType: String?
    let summary: String?
    let status: String

    private enum CodingKeys: String, CodingKey {
        case id
        case title
        case reportType = "report_type"
        case summary
        case status
    }
}

struct RelationRow: Decodable, Identifiable {
    let id: String
    let sourceSummary: String?
    let relationType: String
    let targetSummary: String?

    private enum CodingKeys: String, CodingKey {
        case id
        case sourceSummary = "source_summary"
        case relationType = "relation_type"
        case targetSummary = "target_summary"
    }
}

struct CompiledPayload: Decodable {
    let project: ProjectRecord
    let counts: Counts
    let facts: [FactRow]
    let decisions: [DecisionRow]
    let risks: [RiskRow]
    let openQuestions: [OpenQuestionRow]
    let reports: [ReportRow]
    let relations: [RelationRow]

    private enum CodingKeys: String, CodingKey {
        case project
        case counts
        case facts
        case decisions
        case risks
        case openQuestions = "open_questions"
        case reports
        case relations
    }
}

struct QualityPayload: Decodable {
    let score: Int
    let status: String
    let relationCount: Int
    let relationCoverage: Double
    let factsWithoutSource: [QualityGap]
    let decisionsWithoutRationale: [QualityGap]
    let risksWithoutMitigation: [QualityGap]
    let openQuestions: [OpenQuestionRow]

    private enum CodingKeys: String, CodingKey {
        case score
        case status
        case relationCount = "relation_count"
        case relationCoverage = "relation_coverage"
        case factsWithoutSource = "facts_without_source"
        case decisionsWithoutRationale = "decisions_without_rationale"
        case risksWithoutMitigation = "risks_without_mitigation"
        case openQuestions = "open_questions"
    }
}

struct QualityGap: Decodable, Identifiable {
    let id: String
    let title: String
    let issue: String
}

struct HubViewModel {
    let project: ProjectRecord
    let counts: Counts
    let facts: [FactRow]
    let decisions: [DecisionRow]
    let risks: [RiskRow]
    let openQuestions: [OpenQuestionRow]
    let reports: [ReportRow]
    let relations: [RelationRow]
    let quality: QualityPayload
}
