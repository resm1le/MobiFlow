package com.example.autoa11y.engine

internal object DownloadArtifacts {
    fun matches(fileName: String, baseName: String): Boolean {
        val escaped = Regex.escape(baseName)
        return Regex("""^${escaped}( \(\d+\))?$""").matches(fileName)
    }

    fun findMatches(fileNames: Iterable<String>, baseName: String): List<String> =
        fileNames.filter { matches(it, baseName) }

    fun findMatches(fileNames: Iterable<String>, baseNames: Collection<String>): List<String> =
        fileNames.filter { fileName -> baseNames.any { matches(fileName, it) } }
}
