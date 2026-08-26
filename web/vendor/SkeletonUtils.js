// Vyriznuto z three.js r169 (three/addons/utils/SkeletonUtils.js), MIT.
// Potreba je jen `clone`: scena stavi vic tvoru z jednoho nacteneho GLB a
// prosty Object3D.clone() by vsem nechal spolecnou kostru, takze by se hybali
// jako jeden.

function clone(source) {
	const sourceLookup = new Map();
	const cloneLookup = new Map();

	const cloneNode = source.clone();

	parallelTraverse(source, cloneNode, function (sourceNode, clonedNode) {
		sourceLookup.set(clonedNode, sourceNode);
		cloneLookup.set(sourceNode, clonedNode);
	});

	cloneNode.traverse(function (node) {
		if (!node.isSkinnedMesh) return;

		const clonedMesh = node;
		const sourceMesh = sourceLookup.get(node);
		const sourceBones = sourceMesh.skeleton.bones;

		clonedMesh.skeleton = sourceMesh.skeleton.clone();
		clonedMesh.bindMatrix.copy(sourceMesh.bindMatrix);

		clonedMesh.skeleton.bones = sourceBones.map(function (bone) {
			return cloneLookup.get(bone);
		});

		clonedMesh.bind(clonedMesh.skeleton, clonedMesh.bindMatrix);
	});

	return cloneNode;
}

function parallelTraverse(a, b, callback) {
	callback(a, b);
	for (let i = 0; i < a.children.length; i++) {
		parallelTraverse(a.children[i], b.children[i], callback);
	}
}

export { clone };
