from typing import *
import os
#import logging
import loompy
from scipy import sparse
from scipy.spatial.distance import pdist, squareform
import numpy as np
import networkx as nx
import cytograph as cg
import luigi
import adolescent_mouse as am


class ExportL2(luigi.Task):
	"""
	Luigi Task to export summary files
	"""
	major_class = luigi.Parameter()
	tissue = luigi.Parameter(default="All")
	n_markers = luigi.IntParameter(default=10)

	def requires(self) -> List[luigi.Task]:
		return [
			am.AggregateL2(tissue=self.tissue, major_class=self.major_class),
			am.ClusterL2(tissue=self.tissue, major_class=self.major_class)
		]

	def output(self) -> luigi.Target:
		return luigi.LocalTarget(os.path.join(am.paths().build, "L2_" + self.major_class + "_" + self.tissue + "_exported"))

	def run(self) -> None:
		logging = cg.logging(self, True)
		with self.output().temporary_path() as out_dir:
			logging.info("Exporting cluster data")
			if not os.path.exists(out_dir):
				os.mkdir(out_dir)

			with loompy.connect(self.input()[0].fn) as dsagg:
				logging.info("Computing auto-annotation")
				aa = cg.AutoAnnotator(root=am.paths().autoannotation)
				aa.annotate_loom(dsagg)
				aa.save_in_loom(dsagg)

				dsagg.export(os.path.join(out_dir, "L2_" + self.major_class + "_" + self.tissue + "_expression.tab"))
				dsagg.export(os.path.join(out_dir, "L2_" + self.major_class + "_" + self.tissue + "_enrichment.tab"), layer="enrichment")
				dsagg.export(os.path.join(out_dir, "L2_" + self.major_class + "_" + self.tissue + "_enrichment_q.tab"), layer="enrichment_q")
				dsagg.export(os.path.join(out_dir, "L2_" + self.major_class + "_" + self.tissue + "_trinaries.tab"), layer="trinaries")

				logging.info("Plotting manifold graph with auto-annotation")
				tags = list(dsagg.col_attrs["AutoAnnotation"])
				with loompy.connect(self.input()[1].fn) as ds:
					cg.plot_graph(ds, os.path.join(out_dir, "L2_" + self.major_class + "_" + self.tissue + "_manifold.aa.png"), tags)

					logging.info("Plotting manifold graph with bucket list")
					tags = list(dsagg.col_attrs["Bucket"])
					cg.plot_graph(ds, os.path.join(out_dir, "L2_" + self.major_class + "_" + self.tissue + "_manifold.buckets.png"), tags)
					n_cells = dsagg.ca.NCells
					with open(os.path.join(out_dir, "L2_" + self.major_class + "_" + self.tissue + "_buckets.txt"), 'w') as bf:
						for ix, tag in enumerate(tags):
							bf.write(f"{ix}\t{n_cells[ix]}\t{tag}\t{tag}\t(comment)\n")

					logging.info("Plotting manifold graph with auto-auto-annotation")
					tags = list(dsagg.col_attrs["MarkerGenes"][np.argsort(dsagg.col_attrs["Clusters"])])
					cg.plot_graph(ds, os.path.join(out_dir, "L2_" + self.major_class + "_" + self.tissue + "_manifold.aaa.png"), tags)

					logging.info("Plotting manifold graph with classes")
					cg.plot_classes(ds, os.path.join(out_dir, "L2_" + self.major_class + "_" + self.tissue + "_manifold.classes.png"))

					logging.info("Plotting marker heatmap")
					cg.plot_markerheatmap(ds, dsagg, n_markers_per_cluster=self.n_markers, out_file=os.path.join(out_dir, "L2_" + self.major_class + "_" + self.tissue + "_heatmap.pdf"))

					logging.info("Computing discordance distances")
					pep = 0.05
					n_labels = dsagg.shape[1]

					def discordance_distance(a: np.ndarray, b: np.ndarray) -> float:
						"""
						Number of genes that are discordant with given PEP, divided by number of clusters
						"""
						return np.sum((1 - a) * b + a * (1 - b) > 1 - pep) / n_labels

					data = dsagg.layer["trinaries"][:n_labels * 10, :].T
					D = squareform(pdist(data, discordance_distance))
					with open(os.path.join(out_dir, "L2_" + self.major_class + "_" + self.tissue + "_distances.txt"), "w") as f:
						f.write(str(np.diag(D, k=1)))
