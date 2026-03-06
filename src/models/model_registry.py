"""Model registry for tracking and managing trained models.

Provides version control, metadata tracking, and model lifecycle management
for all trained models in the system.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd


class ModelRegistry:
    """Registry for tracking trained models.
    
    Features:
    - Version tracking and model lineage
    - Metadata storage (training config, metrics)
    - Model promotion (dev -> staging -> prod)
    - Model comparison and selection
    """

    def __init__(self, base_path: str | Path = "models/registry") -> None:
        """Initialize model registry.

        Args:
            base_path: Base directory for model storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        self.models_dir = self.base_path / "models"
        self.metadata_dir = self.base_path / "metadata"
        self.models_dir.mkdir(exist_ok=True)
        self.metadata_dir.mkdir(exist_ok=True)
        
        # Load or create registry index
        self.index_path = self.base_path / "index.json"
        self._load_index()

    def _load_index(self) -> None:
        """Load registry index from disk."""
        if self.index_path.exists():
            with open(self.index_path, 'r') as f:
                self.index = json.load(f)
        else:
            self.index = {
                'models': {},
                'versions': {},
                'tags': {},
            }
            # Save initial index
            self._save_index()

    def _save_index(self) -> None:
        """Save registry index to disk."""
        with open(self.index_path, 'w') as f:
            json.dump(self.index, f, indent=2)

    def register_model(
        self,
        model_name: str,
        model_path: str | Path,
        version: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
    ) -> str:
        """Register a new model.

        Args:
            model_name: Name of the model (e.g., 'garch_gru', 'ensemble')
            model_path: Path to model file
            version: Version string (auto-generated if None)
            metadata: Additional metadata (metrics, config, etc.)
            tags: Tags for categorization

        Returns:
            Version string of registered model
        """
        # Generate version if not provided
        if version is None:
            version = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create model directory
        model_dir = self.models_dir / model_name
        model_dir.mkdir(exist_ok=True)
        
        # Copy model file
        model_path = Path(model_path)
        dest_path = model_dir / f"{version}{model_path.suffix}"
        shutil.copy2(model_path, dest_path)
        
        # Store metadata
        full_metadata = {
            'model_name': model_name,
            'version': version,
            'registered_at': datetime.now().isoformat(),
            'model_path': str(dest_path.relative_to(self.base_path)),
            'original_path': str(model_path),
            'tags': tags or [],
            'status': 'dev',  # dev, staging, prod
        }
        
        if metadata:
            full_metadata.update(metadata)
        
        # Save metadata
        metadata_path = self.metadata_dir / f"{model_name}_{version}.json"
        with open(metadata_path, 'w') as f:
            json.dump(full_metadata, f, indent=2)
        
        # Update index
        if model_name not in self.index['models']:
            self.index['models'][model_name] = []
        
        self.index['models'][model_name].append(version)
        self.index['versions'][f"{model_name}:{version}"] = str(metadata_path.relative_to(self.base_path))
        
        # Update tags
        for tag in (tags or []):
            if tag not in self.index['tags']:
                self.index['tags'][tag] = []
            self.index['tags'][tag].append(f"{model_name}:{version}")
        
        self._save_index()
        
        return version

    def get_model_path(self, model_name: str, version: Optional[str] = None) -> Path:
        """Get path to a registered model.

        Args:
            model_name: Name of the model
            version: Version (uses latest if None)

        Returns:
            Path to model file
        """
        if version is None:
            version = self.get_latest_version(model_name)
        
        metadata = self.get_metadata(model_name, version)
        model_path = self.base_path / metadata['model_path']
        
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        return model_path

    def get_metadata(self, model_name: str, version: str) -> dict[str, Any]:
        """Get metadata for a model version.

        Args:
            model_name: Name of the model
            version: Version string

        Returns:
            Metadata dictionary
        """
        key = f"{model_name}:{version}"
        if key not in self.index['versions']:
            raise ValueError(f"Model not found: {key}")
        
        metadata_path = self.base_path / self.index['versions'][key]
        
        with open(metadata_path, 'r') as f:
            return json.load(f)

    def list_models(self) -> list[str]:
        """List all registered model names.

        Returns:
            List of model names
        """
        return list(self.index['models'].keys())

    def list_versions(self, model_name: str) -> list[str]:
        """List all versions of a model.

        Args:
            model_name: Name of the model

        Returns:
            List of version strings, sorted by date
        """
        if model_name not in self.index['models']:
            return []
        
        return sorted(self.index['models'][model_name])

    def get_latest_version(self, model_name: str) -> str:
        """Get latest version of a model.

        Args:
            model_name: Name of the model

        Returns:
            Latest version string
        """
        versions = self.list_versions(model_name)
        if not versions:
            raise ValueError(f"No versions found for model: {model_name}")
        
        return versions[-1]

    def compare_models(
        self,
        model_versions: list[tuple[str, str]],
        metric: str = 'sharpe_ratio',
    ) -> pd.DataFrame:
        """Compare multiple model versions.

        Args:
            model_versions: List of (model_name, version) tuples
            metric: Metric to compare

        Returns:
            DataFrame with comparison
        """
        data = []
        
        for model_name, version in model_versions:
            metadata = self.get_metadata(model_name, version)
            
            row = {
                'model': model_name,
                'version': version,
                'registered_at': metadata['registered_at'],
                'status': metadata.get('status', 'unknown'),
            }
            
            # Add metrics
            if 'metrics' in metadata:
                for key, value in metadata['metrics'].items():
                    row[key] = value
            
            data.append(row)
        
        df = pd.DataFrame(data)
        
        # Sort by metric if present
        if metric in df.columns:
            df = df.sort_values(metric, ascending=False)
        
        return df

    def promote_model(
        self,
        model_name: str,
        version: str,
        new_status: str,
    ) -> None:
        """Promote model to new status.

        Args:
            model_name: Name of the model
            version: Version to promote
            new_status: New status ('staging' or 'prod')
        """
        if new_status not in ['staging', 'prod']:
            raise ValueError(f"Invalid status: {new_status}")
        
        metadata = self.get_metadata(model_name, version)
        metadata['status'] = new_status
        metadata['promoted_at'] = datetime.now().isoformat()
        
        # Save updated metadata
        key = f"{model_name}:{version}"
        metadata_path = self.base_path / self.index['versions'][key]
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def get_production_model(self, model_name: str) -> Optional[tuple[str, Path]]:
        """Get production version of a model.

        Args:
            model_name: Name of the model

        Returns:
            Tuple of (version, path) or None if no prod version
        """
        versions = self.list_versions(model_name)
        
        for version in reversed(versions):  # Check latest first
            metadata = self.get_metadata(model_name, version)
            if metadata.get('status') == 'prod':
                path = self.get_model_path(model_name, version)
                return version, path
        
        return None

    def delete_model(self, model_name: str, version: str) -> None:
        """Delete a model version.

        Args:
            model_name: Name of the model
            version: Version to delete
        """
        # Check if production
        metadata = self.get_metadata(model_name, version)
        if metadata.get('status') == 'prod':
            raise ValueError("Cannot delete production model. Demote first.")
        
        # Remove files
        model_path = self.get_model_path(model_name, version)
        model_path.unlink()
        
        key = f"{model_name}:{version}"
        metadata_path = self.base_path / self.index['versions'][key]
        metadata_path.unlink()
        
        # Update index
        self.index['models'][model_name].remove(version)
        del self.index['versions'][key]
        
        # Remove from tags
        for tag, models in self.index['tags'].items():
            if key in models:
                models.remove(key)
        
        self._save_index()

    def search_by_tag(self, tag: str) -> list[tuple[str, str]]:
        """Search models by tag.

        Args:
            tag: Tag to search for

        Returns:
            List of (model_name, version) tuples
        """
        if tag not in self.index['tags']:
            return []
        
        results = []
        for key in self.index['tags'][tag]:
            model_name, version = key.split(':')
            results.append((model_name, version))
        
        return results

    def get_best_model(
        self,
        model_type: Optional[str] = None,
        metric: str = 'sharpe_ratio',
        status: Optional[str] = None,
    ) -> Optional[tuple[str, str, float]]:
        """Get best model based on a metric.

        Args:
            model_type: Filter by model type (None for all)
            metric: Metric to optimize
            status: Filter by status (None for all)

        Returns:
            Tuple of (model_name, version, metric_value) or None
        """
        best_model = None
        best_value = float('-inf')
        
        model_names = [model_type] if model_type else self.list_models()
        
        for model_name in model_names:
            for version in self.list_versions(model_name):
                metadata = self.get_metadata(model_name, version)
                
                # Filter by status
                if status and metadata.get('status') != status:
                    continue
                
                # Check metric
                if 'metrics' in metadata and metric in metadata['metrics']:
                    value = metadata['metrics'][metric]
                    if value > best_value:
                        best_value = value
                        best_model = (model_name, version, value)
        
        return best_model

    def export_summary(self) -> dict[str, Any]:
        """Export registry summary.

        Returns:
            Dictionary with registry statistics
        """
        summary = {
            'total_models': len(self.index['models']),
            'total_versions': sum(len(versions) for versions in self.index['models'].values()),
            'models': {},
        }
        
        for model_name in self.list_models():
            versions = self.list_versions(model_name)
            
            # Count by status
            status_counts = {'dev': 0, 'staging': 0, 'prod': 0}
            for version in versions:
                metadata = self.get_metadata(model_name, version)
                status = metadata.get('status', 'dev')
                status_counts[status] += 1
            
            summary['models'][model_name] = {
                'total_versions': len(versions),
                'latest_version': versions[-1] if versions else None,
                'status_counts': status_counts,
            }
        
        return summary
