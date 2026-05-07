def test_keep_keys_includes_essentials():
    from bake.tags_filter import KEEP_KEYS
    expected = {"building", "highway", "landuse", "natural",
                "waterway", "railway", "wikidata", "historic",
                "leaf_type", "genus", "surface"}
    assert expected.issubset(KEEP_KEYS)


def test_filter_command_construction():
    from bake.tags_filter import build_filter_command
    cmd = build_filter_command(input_path="in.pbf", output_path="out.pbf")
    assert "osmium" in cmd[0]
    assert "tags-filter" in cmd
    assert "in.pbf" in cmd
    assert "-o" in cmd or "--output" in cmd
    assert "out.pbf" in cmd


def test_filter_command_includes_overwrite_flag():
    from bake.tags_filter import build_filter_command
    cmd = build_filter_command(input_path="in.pbf", output_path="out.pbf")
    assert "--overwrite" in cmd
