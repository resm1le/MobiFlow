package com.example.autoa11y.engine

import com.example.autoa11y.core.api.Driver
import com.example.autoa11y.core.api.KnownPage
import com.example.autoa11y.core.api.PageSignature

internal class KnownPageResolver(
    private val driver: Driver,
    knownPages: List<KnownPage>
) {
    private val pagesById: Map<String, KnownPage> = knownPages.associateBy { it.id }
    private val pagesInOrder: List<KnownPage> = knownPages

    fun pageById(id: String): KnownPage? = pagesById[id]

    fun resolveCurrentPage(): KnownPage? =
        pagesInOrder.firstOrNull { matches(it.sig) }

    fun waitForPage(id: String, timeoutMs: Long): KnownPage? {
        val target = pageById(id) ?: return null
        if (timeoutMs <= 0L) {
            return if (matches(target.sig)) target else null
        }

        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (matches(target.sig)) return target
            Thread.sleep(200L)
        }
        return null
    }

    fun matches(sig: PageSignature): Boolean {
        if (sig.must.isNotEmpty() && !sig.must.all { driver.waitVisible(it, 0) }) return false
        if (sig.oneOf.isNotEmpty() && !sig.oneOf.any { driver.waitVisible(it, 0) }) return false
        if (sig.mustNot.isNotEmpty() && sig.mustNot.any { driver.waitVisible(it, 0) }) return false
        return true
    }
}
