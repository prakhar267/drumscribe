.PHONY: ci ci-fast

ci:
	./scripts/ci.sh

ci-fast:
	DRUMSCRIBE_SKIP_DEPENDENCY_AUDIT=1 ./scripts/ci.sh
