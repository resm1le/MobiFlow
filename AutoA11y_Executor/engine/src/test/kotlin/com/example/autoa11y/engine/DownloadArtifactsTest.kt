package com.example.autoa11y.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DownloadArtifactsTest {

    @Test
    fun `matches exact base name and drive duplicate suffix`() {
        assertTrue(DownloadArtifacts.matches("004_smoke_zip.zip", "004_smoke_zip.zip"))
        assertTrue(DownloadArtifacts.matches("004_smoke_zip.zip (1)", "004_smoke_zip.zip"))
        assertTrue(DownloadArtifacts.matches("004_smoke_zip.zip (12)", "004_smoke_zip.zip"))
        assertFalse(DownloadArtifacts.matches("004_smoke_zip(1).zip", "004_smoke_zip.zip"))
    }

    @Test
    fun `findMatches filters against multiple base names`() {
        val files = listOf(
            "004_smoke_zip.zip",
            "004_smoke_zip.zip (1)",
            "002_smoke_pdf.pdf",
            "random.bin"
        )

        assertEquals(
            listOf("004_smoke_zip.zip", "004_smoke_zip.zip (1)", "002_smoke_pdf.pdf"),
            DownloadArtifacts.findMatches(files, listOf("004_smoke_zip.zip", "002_smoke_pdf.pdf"))
        )
    }
}
