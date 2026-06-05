// swift-tools-version: 5.10

import PackageDescription

let package = Package(
    name: "HubView",
    platforms: [
        .macOS(.v14),
    ],
    products: [
        .executable(name: "HubViewApp", targets: ["HubViewApp"]),
    ],
    targets: [
        .executableTarget(
            name: "HubViewApp"
        ),
        .testTarget(
            name: "HubViewAppTests",
            dependencies: ["HubViewApp"]
        ),
    ]
)
