# DuckDB floor verification — 2026-10-07

Candidate: main `0b92561` plus the exact 27-module mypy registration.

Python 3.11.15; DuckDB 1.2.0; offline test run, exit 0. The preserved
35-function policy/facade/classification selector set expanded to 62 cases.
No case was excluded. An existing synthetic HOME was empty before and after.
Bytecode writing was disabled for this isolated floor run.

Each case below is from `tests/index/test_store.py`.

| Case | Result |
| --- | --- |
| `test_policy_constants_match_the_connection_contract` | PASS |
| `test_public_fault_and_result_contracts_are_typed_and_frozen` | PASS |
| `test_every_connection_applies_all_mandatory_settings` | PASS |
| `test_matching_mandatory_override_is_allowed` | PASS |
| `test_writer_and_reader_config_composition_is_explicit` | PASS |
| `test_open_forwards_complete_path_mode_and_config_to_connection_backend` | PASS |
| `test_facade_wraps_original_backend_errors_for_every_operation[execute-False]` | PASS |
| `test_facade_wraps_original_backend_errors_for_every_operation[execute-True]` | PASS |
| `test_facade_wraps_original_backend_errors_for_every_operation[fetchmany-False]` | PASS |
| `test_facade_wraps_original_backend_errors_for_every_operation[fetchmany-True]` | PASS |
| `test_facade_wraps_original_backend_errors_for_every_operation[fetchall-False]` | PASS |
| `test_facade_wraps_original_backend_errors_for_every_operation[fetchall-True]` | PASS |
| `test_open_error_preserves_original_backend_exception[False]` | PASS |
| `test_open_error_preserves_original_backend_exception[True]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[False-autoinstall_known_extensions-True]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[False-autoload_known_extensions-True]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[False-allow_community_extensions-True]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[False-allow_persistent_secrets-True]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[False-enable_external_access-True]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[False-python_enable_replacements-True]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[False-lock_configuration-False]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[True-autoinstall_known_extensions-True]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[True-autoload_known_extensions-True]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[True-allow_community_extensions-True]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[True-allow_persistent_secrets-True]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[True-enable_external_access-True]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[True-python_enable_replacements-True]` | PASS |
| `test_mandatory_override_is_refused_before_path_creation[True-lock_configuration-False]` | PASS |
| `test_create_refuses_existing_index_without_changing_bytes` | PASS |
| `test_create_refuses_dangling_symlink_without_touching_target` | PASS |
| `test_writers_use_compatibility_and_named_spill_directory` | PASS |
| `test_created_database_header_uses_storage_version_64` | PASS |
| `test_external_and_configuration_statements_are_refused_without_home_writes[SET enable_external_access = true]` | PASS |
| `test_external_and_configuration_statements_are_refused_without_home_writes[SET autoinstall_known_extensions = true]` | PASS |
| `test_external_and_configuration_statements_are_refused_without_home_writes[SELECT * FROM read_csv('/etc/hosts')]` | PASS |
| `test_external_and_configuration_statements_are_refused_without_home_writes[SELECT * FROM read_csv('https://example.invalid/x.csv')]` | PASS |
| `test_https_parameter_round_trips_as_plain_text` | PASS |
| `test_multiple_heterogeneous_parameters_round_trip` | PASS |
| `test_fetchmany_honors_repeated_sizes_and_fetchall_returns_remainder` | PASS |
| `test_idle_interrupt_is_harmless` | PASS |
| `test_result_columns_keep_name_and_type_and_execute_errors_chain` | PASS |
| `test_nonquery_results_have_no_columns_or_rows` | PASS |
| `test_read_only_connection_refuses_write` | PASS |
| `test_context_manager_closes_connection_even_when_body_raises` | PASS |
| `test_open_errors_expose_other_fault_for_later_classification` | PASS |
| `test_fetch_conversion_errors_are_wrapped_and_chained[fetchmany]` | PASS |
| `test_fetch_conversion_errors_are_wrapped_and_chained[fetchall]` | PASS |
| `test_interrupt_during_execute_or_fetch_is_wrapped_in_bounded_subprocess` | PASS |
| `test_duckdb_version_comes_from_installed_distribution_metadata` | PASS |
| `test_created_connection_can_be_used_as_context_manager` | PASS |
| `test_classifies_read_write_lock_and_extracts_holder_pid` | PASS |
| `test_classifies_read_only_lock_when_writer_attempts_open` | PASS |
| `test_classifies_missing_database[False-True-database does not exist]` | PASS |
| `test_classifies_missing_database[True-False-No such file or directory]` | PASS |
| `test_classifies_corrupt_database_files[junk-is not a valid DuckDB database file]` | PASS |
| `test_classifies_corrupt_database_files[empty-is not a valid DuckDB database file]` | PASS |
| `test_classifies_corrupt_database_files[truncated-Could not read enough bytes]` | PASS |
| `test_classifies_corrupt_database_files[flipped-Corrupt database file]` | PASS |
| `test_classifies_forged_storage_version_as_incompatible` | PASS |
| `test_classifies_unrecognized_duckdb_statement_as_other` | PASS |
| `test_non_duckdb_exception_with_lock_stem_is_other` | PASS |
| `test_locked_duckdb_error_without_pid_preserves_message_and_cause` | PASS |


Raw commands, selectors, output and HOME/version checks:
`/private/tmp/analytics-index-evidence/verification-polling/local/`.
