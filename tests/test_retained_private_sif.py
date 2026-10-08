"""Execute the real plan policy across private and public authority boundaries."""

import copy

import pytest
from test_sif_matrix_contract import DEV, SAC, blocks, contract, node, registry


def private_image(*, pg=False):
    capabilities = {'postgres': '18.6' if pg else '16.15'}
    if not pg:
        capabilities.update({'3.11': '3.11.16', '3.12': '3.12.14', '3.13': '3.13.15'})
    return {
        'authority_kind': 'retained-private-ci',
        'sha256': 'a' * 64,
        'bytes': 100,
        'qualification_sha256': 'b' * 64,
        'capabilities': capabilities,
        'native_paths': ['/retained/pg.sif' if pg else '/retained/ci.sif'],
    }


def private_registry():
    records = registry()
    for repository in (DEV, SAC):
        records[repository]['nativeImage'] = private_image()
        records[repository]['image'] = None
        records[repository]['hostedRuntime'] = None
    records[SAC]['nativePgImage'] = private_image(pg=True)
    records[SAC]['pgImage'] = None
    return records


def test_actual_registered_dev_retains_three_minors_and_exact_private_source_gate():
    # Arrange
    # Act
    result = contract('plan')
    # Assert
    assert result['ok'] and (
        result['value']['versions'],
        result['value']['image']['sha256'],
        result['value']['leafSources']['.github/ci/verify-postgres-capability.py'],
    ) == (
        ['3.11', '3.12', '3.13'],
        'aa5836a6c317640d7e20f01eb79aa7385b3dca2f369b595065c50ba3dd34a7d5',
        'af610a811b19f746c9a717fbebbc67639b16df962544acac9b51a3dd38a43455',
    )


@pytest.mark.parametrize(
    'event,versions',
        [('pull_request', ['3.11', '3.12', '3.13']), ('push', ['3.11', '3.12', '3.13'])],
)
def test_actual_sac_plan_requires_separate_pg18_and_keeps_original_matrix(
    event, versions
):
    # Arrange
    # Act
    result = contract('plan', repository=SAC, event=event)
    # Assert
    assert result['ok'] and (
        result['value']['versions'],
        result['value']['image']['capabilities']['postgres'],
        result['value']['pgImage']['sha256'],
        result['value']['pgVersion'],
        result['value']['leafSources']['.github/ci/clean-tmpdir.sh'],
    ) == (
        versions,
        '16.15',
        '842a1fcf5abdc512af312c1527a0700c52e4b1a6b6e3e3dddc6edde69113ee23',
        '18.6',
        '36421082132cf7b48564bce71470f7c2b0483cb72286ae2710f7e7dd62f3962a',
    )


def test_actual_sac_private_profile_does_not_enable_public_or_fork_delivery():
    # Arrange
    # Act
    result = contract('plan', repository=SAC, native=False)
    # Assert
    assert result == {'ok': False, 'reason': 'image-unqualified'}


@pytest.mark.parametrize('repository', [DEV, SAC])
def test_authorized_native_uses_private_pins_without_public_producer_claim(repository):
    # Arrange
    records = private_registry()
    # Act
    result = contract('plan', repository=repository, registry=records)
    # Assert
    assert (
        result['ok']
        and result['value']['image'] == records[repository]['nativeImage']
        and 'producer_revision' not in result['value']['image']
    )


@pytest.mark.parametrize('repository', [DEV, SAC])
def test_unconfirmed_or_fork_route_cannot_receive_the_same_private_registry(repository):
    # Arrange
    records = private_registry()
    # Act
    result = contract('plan', repository=repository, native=False, registry=records)
    # Assert
    assert result == {'ok': False, 'reason': 'image-unqualified'}


def test_private_pg_image_cannot_replace_a_missing_hosted_pg_image():
    # Arrange
    records = registry()
    records[SAC]['nativePgImage'] = private_image(pg=True)
    records[SAC]['pgImage'] = None
    # Act
    result = contract('plan', repository=SAC, native=False, registry=records)
    # Assert
    assert result == {'ok': False, 'reason': 'image-unqualified'}


def test_existing_public_full_plan_is_selected_even_if_private_pins_exist():
    # Arrange
    records = registry()
    original = copy.deepcopy(records[DEV]['image'])
    records[DEV]['nativeImage'] = private_image()
    # Act
    result = contract('plan', native=False, registry=records)
    # Assert
    assert result['ok'] and (
        result['value']['image'], result['value']['versions']
    ) == (original, ['3.11', '3.12', '3.13'])


def test_private_payload_cannot_impersonate_the_public_image_contract():
    # Arrange
    records = private_registry()
    records[DEV]['image'] = records[DEV]['nativeImage']
    # Act
    result = contract('plan', native=False, registry=records)
    # Assert
    assert result == {'ok': False, 'reason': 'image-unqualified'}


@pytest.mark.parametrize(
    'field,value,reason',
    [
        ('authority_kind', 'public', 'private-image-authority-unqualified'),
        ('sha256', None, 'private-image-byte-pin-invalid'),
        ('bytes', 0, 'private-image-byte-pin-invalid'),
        ('bytes', 32 * 1024**3 + 1, 'private-image-byte-pin-invalid'),
        ('qualification_sha256', None, 'private-image-byte-pin-invalid'),
        ('capabilities', {'postgres': '16.15'}, 'private-image-capabilities-unqualified'),
        ('native_paths', [], 'private-image-locator-unqualified'),
        ('native_paths', ['/retained/../ci.sif'], 'private-image-locator-unqualified'),
        ('native_paths', ['https://example.invalid/ci.sif'], 'private-image-locator-unqualified'),
        ('native_paths', ['/retained/ci.sif'] * 2, 'private-image-locator-unqualified'),
    ],
)
def test_unknown_authority_bytes_capability_or_path_refuses_before_a_leaf_job(
    field, value, reason
):
    # Arrange
    records = private_registry()
    records[DEV]['nativeImage'][field] = value
    # Act
    result = contract('plan', registry=records)
    # Assert
    assert result == {'ok': False, 'reason': reason}


def test_private_admission_never_bypasses_leaf_source_qualification():
    # Arrange
    records = private_registry()
    records[DEV]['leafSources'].pop('.github/ci/verify-postgres-capability.py')
    # Act
    result = contract('plan', registry=records)
    # Assert
    assert result == {'ok': False, 'reason': 'leaf-source-closure-unqualified'}


def test_private_admission_never_bypasses_runtime_namespace_qualification():
    # Arrange
    records = private_registry()
    records[DEV]['nativeRuntime']['user_namespace'] = False
    # Act
    result = contract('plan', registry=records)
    # Assert
    assert result == {'ok': False, 'reason': 'runtime-capability-unqualified'}


def test_private_pg16_cannot_replace_sacs_required_pg18():
    # Arrange
    records = private_registry()
    records[SAC]['nativePgImage']['capabilities']['postgres'] = '16.15'
    # Act
    result = contract('plan', repository=SAC, registry=records)
    # Assert
    assert result == {'ok': False, 'reason': 'sac-pg18-unqualified'}


def test_nightly_never_selects_native_private_execution():
    # Arrange
    records = private_registry()
    # Act
    result = contract('plan', repository=SAC, registry=records, suite='nightly')
    # Assert
    assert result == {'ok': False, 'reason': 'nightly-native-refused'}


def test_private_image_qualifier_independently_refuses_hosted_use():
    # Arrange
    program = blocks('SIF_CONTRACT')[0] + '''
try {
  qualifyRetainedPrivateImage(JSON.parse(process.argv[1]), false);
  console.log(JSON.stringify({accepted: true}));
} catch (error) { console.log(JSON.stringify({reason: error.message})); }
'''
    # Act
    result = node(program, private_image())
    # Assert
    assert result == {'reason': 'private-image-hosted-refused'}
