import Foundation
import Vision
import AppKit

// Texte uniquement : aucune analyse visuelle n'est prétendue.
do {
    guard CommandLine.arguments.count == 2 else { exit(1) }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["fr-FR", "en-US"]
    request.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(url: URL(fileURLWithPath: CommandLine.arguments[1]))
    try handler.perform([request])
    for observation in request.results ?? [] {
        if let candidate = observation.topCandidates(1).first { print(candidate.string) }
    }
} catch {
    fputs("Lecture de l'image impossible.\n", stderr)
    exit(1)
}
