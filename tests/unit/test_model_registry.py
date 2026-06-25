"""Tests for model registry."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from trainer.models.model_registry import ModelRegistry


@pytest.fixture
def temp_registry():
    """Create temporary registry for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = ModelRegistry(base_path=tmpdir)
        yield registry


@pytest.fixture
def sample_model_file():
    """Create a temporary model file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pkl', delete=False) as f:
        f.write("dummy model data")
        return Path(f.name)


def test_registry_init(temp_registry):
    """Test registry initialization."""
    assert temp_registry.base_path.exists()
    assert temp_registry.models_dir.exists()
    assert temp_registry.metadata_dir.exists()
    assert temp_registry.index_path.exists()


def test_register_model(temp_registry, sample_model_file):
    """Test registering a model."""
    version = temp_registry.register_model(
        model_name='test_model',
        model_path=sample_model_file,
        metadata={'accuracy': 0.95},
        tags=['test', 'baseline'],
    )
    
    assert version is not None
    assert 'test_model' in temp_registry.list_models()
    assert version in temp_registry.list_versions('test_model')


def test_register_model_with_custom_version(temp_registry, sample_model_file):
    """Test registering model with custom version."""
    version = temp_registry.register_model(
        model_name='test_model',
        model_path=sample_model_file,
        version='v1.0.0',
    )
    
    assert version == 'v1.0.0'


def test_register_multiple_versions(temp_registry, sample_model_file):
    """Test registering multiple versions of same model."""
    v1 = temp_registry.register_model(
        model_name='model1',
        model_path=sample_model_file,
        version='v1',
    )
    
    v2 = temp_registry.register_model(
        model_name='model1',
        model_path=sample_model_file,
        version='v2',
    )
    
    versions = temp_registry.list_versions('model1')
    assert len(versions) == 2
    assert 'v1' in versions
    assert 'v2' in versions


def test_get_model_path(temp_registry, sample_model_file):
    """Test getting model path."""
    version = temp_registry.register_model(
        model_name='test_model',
        model_path=sample_model_file,
    )
    
    path = temp_registry.get_model_path('test_model', version)
    
    assert path.exists()
    assert path.suffix == '.pkl'


def test_get_model_path_latest(temp_registry, sample_model_file):
    """Test getting latest model path."""
    temp_registry.register_model(
        model_name='model1',
        model_path=sample_model_file,
        version='v1',
    )
    
    temp_registry.register_model(
        model_name='model1',
        model_path=sample_model_file,
        version='v2',
    )
    
    # Get latest (no version specified)
    path = temp_registry.get_model_path('model1')
    
    assert 'v2' in str(path)


def test_get_metadata(temp_registry, sample_model_file):
    """Test getting model metadata."""
    version = temp_registry.register_model(
        model_name='test_model',
        model_path=sample_model_file,
        metadata={'sharpe_ratio': 1.5, 'win_rate': 0.55},
        tags=['production'],
    )
    
    metadata = temp_registry.get_metadata('test_model', version)
    
    assert metadata['model_name'] == 'test_model'
    assert metadata['version'] == version
    assert metadata['sharpe_ratio'] == 1.5
    assert metadata['win_rate'] == 0.55
    assert 'production' in metadata['tags']
    assert metadata['status'] == 'dev'


def test_get_metadata_not_found(temp_registry):
    """Test that getting non-existent metadata raises error."""
    with pytest.raises(ValueError, match="Model not found"):
        temp_registry.get_metadata('nonexistent', 'v1')


def test_list_models(temp_registry, sample_model_file):
    """Test listing models."""
    temp_registry.register_model('model1', sample_model_file)
    temp_registry.register_model('model2', sample_model_file)
    temp_registry.register_model('model3', sample_model_file)
    
    models = temp_registry.list_models()
    
    assert len(models) == 3
    assert 'model1' in models
    assert 'model2' in models
    assert 'model3' in models


def test_list_versions(temp_registry, sample_model_file):
    """Test listing versions."""
    temp_registry.register_model('model1', sample_model_file, version='v1')
    temp_registry.register_model('model1', sample_model_file, version='v2')
    temp_registry.register_model('model1', sample_model_file, version='v3')
    
    versions = temp_registry.list_versions('model1')
    
    assert len(versions) == 3
    # Should be sorted
    assert versions == ['v1', 'v2', 'v3']


def test_list_versions_empty(temp_registry):
    """Test listing versions for non-existent model."""
    versions = temp_registry.list_versions('nonexistent')
    assert versions == []


def test_get_latest_version(temp_registry, sample_model_file):
    """Test getting latest version."""
    temp_registry.register_model('model1', sample_model_file, version='v1')
    temp_registry.register_model('model1', sample_model_file, version='v2')
    temp_registry.register_model('model1', sample_model_file, version='v3')
    
    latest = temp_registry.get_latest_version('model1')
    
    assert latest == 'v3'


def test_get_latest_version_not_found(temp_registry):
    """Test that getting latest of non-existent model raises error."""
    with pytest.raises(ValueError, match="No versions found"):
        temp_registry.get_latest_version('nonexistent')


def test_compare_models(temp_registry, sample_model_file):
    """Test comparing models."""
    temp_registry.register_model(
        'model1',
        sample_model_file,
        version='v1',
        metadata={'metrics': {'sharpe_ratio': 1.5, 'win_rate': 0.55}}
    )
    
    temp_registry.register_model(
        'model2',
        sample_model_file,
        version='v1',
        metadata={'metrics': {'sharpe_ratio': 1.8, 'win_rate': 0.60}}
    )
    
    comparison = temp_registry.compare_models(
        [('model1', 'v1'), ('model2', 'v1')],
        metric='sharpe_ratio'
    )
    
    assert len(comparison) == 2
    assert 'sharpe_ratio' in comparison.columns
    assert 'win_rate' in comparison.columns
    # Should be sorted by sharpe_ratio descending
    assert comparison.iloc[0]['model'] == 'model2'


def test_promote_model(temp_registry, sample_model_file):
    """Test promoting model to different status."""
    version = temp_registry.register_model(
        'model1',
        sample_model_file,
    )
    
    # Initially dev
    metadata = temp_registry.get_metadata('model1', version)
    assert metadata['status'] == 'dev'
    
    # Promote to staging
    temp_registry.promote_model('model1', version, 'staging')
    metadata = temp_registry.get_metadata('model1', version)
    assert metadata['status'] == 'staging'
    
    # Promote to prod
    temp_registry.promote_model('model1', version, 'prod')
    metadata = temp_registry.get_metadata('model1', version)
    assert metadata['status'] == 'prod'


def test_promote_model_invalid_status(temp_registry, sample_model_file):
    """Test that invalid status raises error."""
    version = temp_registry.register_model('model1', sample_model_file)
    
    with pytest.raises(ValueError, match="Invalid status"):
        temp_registry.promote_model('model1', version, 'invalid')


def test_get_production_model(temp_registry, sample_model_file):
    """Test getting production model."""
    v1 = temp_registry.register_model('model1', sample_model_file, version='v1')
    v2 = temp_registry.register_model('model1', sample_model_file, version='v2')
    
    # Promote v2 to prod
    temp_registry.promote_model('model1', 'v2', 'prod')
    
    result = temp_registry.get_production_model('model1')
    
    assert result is not None
    version, path = result
    assert version == 'v2'
    assert path.exists()


def test_get_production_model_none(temp_registry, sample_model_file):
    """Test getting production model when none exists."""
    temp_registry.register_model('model1', sample_model_file)
    
    result = temp_registry.get_production_model('model1')
    
    assert result is None


def test_delete_model(temp_registry, sample_model_file):
    """Test deleting a model."""
    version = temp_registry.register_model('model1', sample_model_file)
    
    assert version in temp_registry.list_versions('model1')
    
    temp_registry.delete_model('model1', version)
    
    assert version not in temp_registry.list_versions('model1')


def test_delete_production_model_raises_error(temp_registry, sample_model_file):
    """Test that deleting production model raises error."""
    version = temp_registry.register_model('model1', sample_model_file)
    temp_registry.promote_model('model1', version, 'prod')
    
    with pytest.raises(ValueError, match="Cannot delete production"):
        temp_registry.delete_model('model1', version)


def test_search_by_tag(temp_registry, sample_model_file):
    """Test searching models by tag."""
    temp_registry.register_model(
        'model1',
        sample_model_file,
        version='v1',
        tags=['baseline', 'fast']
    )
    
    temp_registry.register_model(
        'model2',
        sample_model_file,
        version='v1',
        tags=['ensemble', 'fast']
    )
    
    temp_registry.register_model(
        'model3',
        sample_model_file,
        version='v1',
        tags=['baseline']
    )
    
    # Search for 'fast'
    results = temp_registry.search_by_tag('fast')
    assert len(results) == 2
    
    # Search for 'baseline'
    results = temp_registry.search_by_tag('baseline')
    assert len(results) == 2
    
    # Search for 'ensemble'
    results = temp_registry.search_by_tag('ensemble')
    assert len(results) == 1


def test_search_by_tag_not_found(temp_registry):
    """Test searching for non-existent tag."""
    results = temp_registry.search_by_tag('nonexistent')
    assert results == []


def test_get_best_model(temp_registry, sample_model_file):
    """Test getting best model by metric."""
    temp_registry.register_model(
        'model1',
        sample_model_file,
        version='v1',
        metadata={'metrics': {'sharpe_ratio': 1.5}}
    )
    
    temp_registry.register_model(
        'model2',
        sample_model_file,
        version='v1',
        metadata={'metrics': {'sharpe_ratio': 1.8}}
    )
    
    temp_registry.register_model(
        'model3',
        sample_model_file,
        version='v1',
        metadata={'metrics': {'sharpe_ratio': 1.2}}
    )
    
    best = temp_registry.get_best_model(metric='sharpe_ratio')
    
    assert best is not None
    model_name, version, value = best
    assert model_name == 'model2'
    assert value == 1.8


def test_get_best_model_with_filter(temp_registry, sample_model_file):
    """Test getting best model with status filter."""
    temp_registry.register_model(
        'model1',
        sample_model_file,
        version='v1',
        metadata={'metrics': {'sharpe_ratio': 1.5}}
    )
    
    temp_registry.register_model(
        'model2',
        sample_model_file,
        version='v1',
        metadata={'metrics': {'sharpe_ratio': 1.8}}
    )
    
    # Promote model1 to prod
    temp_registry.promote_model('model1', 'v1', 'prod')
    
    # Get best prod model
    best = temp_registry.get_best_model(metric='sharpe_ratio', status='prod')
    
    assert best is not None
    model_name, version, value = best
    assert model_name == 'model1'  # Only prod model


def test_get_best_model_none(temp_registry):
    """Test getting best model when none exists."""
    best = temp_registry.get_best_model(metric='sharpe_ratio')
    assert best is None


def test_export_summary(temp_registry, sample_model_file):
    """Test exporting registry summary."""
    temp_registry.register_model('model1', sample_model_file, version='v1')
    temp_registry.register_model('model1', sample_model_file, version='v2')
    temp_registry.register_model('model2', sample_model_file, version='v1')
    
    temp_registry.promote_model('model1', 'v2', 'prod')
    
    summary = temp_registry.export_summary()
    
    assert summary['total_models'] == 2
    assert summary['total_versions'] == 3
    assert 'model1' in summary['models']
    assert summary['models']['model1']['total_versions'] == 2
    assert summary['models']['model1']['latest_version'] == 'v2'
    assert summary['models']['model1']['status_counts']['prod'] == 1


def test_registry_persistence(sample_model_file):
    """Test that registry persists across instances."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create registry and add model
        registry1 = ModelRegistry(base_path=tmpdir)
        version = registry1.register_model('model1', sample_model_file)
        
        # Create new registry instance with same path
        registry2 = ModelRegistry(base_path=tmpdir)
        
        # Should have same data
        assert 'model1' in registry2.list_models()
        assert version in registry2.list_versions('model1')


def test_model_path_not_found_raises_error(temp_registry, sample_model_file):
    """Test that missing model file raises error."""
    version = temp_registry.register_model('model1', sample_model_file)
    
    # Delete the actual model file
    model_path = temp_registry.get_model_path('model1', version)
    model_path.unlink()
    
    with pytest.raises(FileNotFoundError):
        temp_registry.get_model_path('model1', version)
